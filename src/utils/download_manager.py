import logging
from pathlib import Path
from telegram import Update, Message
from telegram.error import BadRequest
from ..downloaders import DownloadError
import asyncio
from functools import partial
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
import aiohttp
from typing import Dict, Optional, Set
import time
from collections import defaultdict

# Configure logging to prevent duplicates
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

class DownloadWorker:
    """Worker class to handle individual downloads"""
    def __init__(self, localization, settings_manager, session: aiohttp.ClientSession):
        self.localization = localization
        self.settings_manager = settings_manager
        self.session = session
        self._status_queue = asyncio.Queue()
        self._stop_event = asyncio.Event()
        self._current_message: Optional[Message] = None
        self._current_user_id: Optional[int] = None
        self._last_status: Optional[str] = None
        self._last_progress: Optional[int] = None
        self._status_task: Optional[asyncio.Task] = None
        self._last_update_time = 0
        self._update_interval = 0.5  # Minimum time between status updates

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        language = settings.language
        return self.localization.get(language, key, **kwargs)

    async def update_status(self, message: Message, user_id: int, status_key: str, progress: int):
        """Update status message with current progress"""
        try:
            # Rate limit status updates
            current_time = time.time()
            if current_time - self._last_update_time < self._update_interval:
                return

            new_text = self.get_message(user_id, status_key, progress=progress)
            if new_text == self._last_status and progress == self._last_progress:
                return

            try:
                await asyncio.wait_for(message.edit_text(new_text), timeout=2.0)
                self._last_status = new_text
                self._last_progress = progress
                self._last_update_time = current_time
            except asyncio.TimeoutError:
                logger.debug("Status update timed out, skipping")
            except BadRequest as e:
                if "Message is not modified" not in str(e):
                    logger.error(f"Error updating status: {e}")
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    async def _process_status_updates(self):
        """Process status updates asynchronously"""
        try:
            while not self._stop_event.is_set():
                try:
                    status, progress = await asyncio.wait_for(
                        self._status_queue.get(),
                        timeout=0.1
                    )
                    if status == "STOP":
                        break

                    if self._current_message and self._current_user_id:
                        await self.update_status(
                            self._current_message,
                            self._current_user_id,
                            status,
                            progress
                        )
                        self._status_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing status update: {e}")
        except asyncio.CancelledError:
            pass

    async def progress_callback(self, status: str, progress: int):
        """Async callback for progress updates"""
        try:
            await self._status_queue.put((status, progress))
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

    async def process_download(self, downloader, url: str, update: Update, status_message: Message, format_id: str = None) -> None:
        """Process content download with error handling and cleanup"""
        user_id = update.effective_user.id
        file_path = None

        try:
            logger.info(f"Starting download for URL: {url}")
            
            # Reset state
            self._last_status = None
            self._last_progress = None
            self._current_message = status_message
            self._current_user_id = user_id
            self._stop_event.clear()
            self._last_update_time = 0
            
            # Start status update task
            self._status_task = asyncio.create_task(self._process_status_updates())
            
            # Set up progress callback
            downloader.set_progress_callback(self.progress_callback)
            
            # Initial status
            await self.update_status(status_message, user_id, 'status_getting_info', 0)
            
            # Download content
            metadata, file_path = await downloader.download(url, format_id)
            logger.info(f"Download completed. File path: {file_path}")
            
            # Sending phase
            await self.update_status(status_message, user_id, 'status_sending', 0)
            logger.info("Sending file to Telegram...")
            
            with open(file_path, 'rb') as file:
                if file_path.suffix.lower() in ['.mp3', '.m4a', '.wav']:
                    await update.effective_message.reply_audio(
                        audio=file,
                        caption=metadata,
                        parse_mode='HTML',
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )
                else:
                    await update.effective_message.reply_video(
                        video=file,
                        caption=metadata,
                        parse_mode='HTML',
                        supports_streaming=True,
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )
            await self.update_status(status_message, user_id, 'status_sending', 100)
            logger.info("File sent successfully")

        except DownloadError as e:
            error_message = str(e)
            await update.effective_message.reply_text(
                self.get_message(user_id, 'download_failed', error=error_message)
            )
            logger.error(f"Download error for {url}: {error_message}")

        except Exception as e:
            await update.effective_message.reply_text(
                self.get_message(user_id, 'error_occurred')
            )
            logger.error(f"Unexpected error processing {url}: {e}", exc_info=True)

        finally:
            # Stop status update task
            self._stop_event.set()
            if self._status_task:
                await self._status_queue.put(("STOP", 0))
                self._status_task.cancel()
                try:
                    await self._status_task
                except asyncio.CancelledError:
                    pass

            # Clear state
            self._current_message = None
            self._current_user_id = None
            self._last_status = None
            self._last_progress = None

            # Cleanup downloaded file
            if file_path:
                try:
                    Path(file_path).unlink()
                    logger.info(f"Cleaned up file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {e}")

            # Delete status message
            try:
                await status_message.delete()
                logger.info("Status message deleted")
            except Exception as e:
                logger.error(f"Error deleting status message: {e}")

class DownloadManager:
    """High-performance download manager with optimized concurrency"""
    def __init__(self, localization, settings_manager, max_concurrent_downloads=50, max_downloads_per_user=5):
        self.localization = localization
        self.settings_manager = settings_manager
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_downloads_per_user = max_downloads_per_user
        
        # Initialize as None, will create when needed
        self.connector = None
        self.session = None
        self._initialized = False
        
        # Active downloads tracking
        self.active_downloads: Dict[int, Dict[str, asyncio.Task]] = defaultdict(dict)
        self._downloads_lock = None
        
        # Download queue
        self.download_queue = None
        self._queue_processor_task = None
        self._queue_processor_running = False
        
        # Rate limiting per domain
        self.rate_limits: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(10)  # Increased from 5 to 10
        )

    async def _create_queue(self):
        """Create a new queue bound to the current event loop"""
        try:
            if self.download_queue:
                # Wait for existing queue to empty
                try:
                    await asyncio.wait_for(self.download_queue.join(), timeout=5.0)
                except (asyncio.TimeoutError, Exception):
                    pass
            # Create new queue bound to current event loop
            self.download_queue = asyncio.PriorityQueue()
        except Exception as e:
            logger.error(f"Error creating queue: {e}")
            raise

    async def _ensure_initialized(self):
        """Ensure manager is initialized with event loop"""
        if not self._initialized:
            self.connector = aiohttp.TCPConnector(
                limit=self.max_concurrent_downloads,
                limit_per_host=20,  # Increased from 10 to 20
                enable_cleanup_closed=True,
                force_close=True,
                ttl_dns_cache=300
            )
            
            self.session = aiohttp.ClientSession(
                connector=self.connector,
                timeout=aiohttp.ClientTimeout(total=300),
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
            
            self._downloads_lock = asyncio.Lock()
            await self._create_queue()
            # Start queue processor
            self._queue_processor_running = True
            self._queue_processor_task = asyncio.create_task(self._process_queue())
            self._initialized = True

    async def _process_queue(self):
        """Process the download queue"""
        while self._queue_processor_running:
            try:
                _, worker, args = await self.download_queue.get()
                try:
                    await worker.process_download(*args)
                finally:
                    self.download_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing download queue: {e}")
                # Recreate queue if it's bound to wrong event loop
                if "is bound to a different event loop" in str(e):
                    try:
                        await self._create_queue()
                    except Exception as create_error:
                        logger.error(f"Error recreating queue: {create_error}")
                    continue

    async def process_download(self, downloader, url: str, update: Update, status_message: Message, format_id: str = None) -> None:
        """Process download request with optimized performance"""
        await self._ensure_initialized()
        
        user_id = update.effective_user.id
        
        async with self._downloads_lock:
            # Clean up completed downloads
            for uid, downloads in list(self.active_downloads.items()):
                self.active_downloads[uid] = {
                    url: task for url, task in downloads.items()
                    if not task.done()
                }
                if not self.active_downloads[uid]:
                    del self.active_downloads[uid]
            
            # Check user's concurrent downloads limit
            if len(self.active_downloads.get(user_id, {})) >= self.max_downloads_per_user:
                await status_message.edit_text(
                    DownloadWorker(self.localization, self.settings_manager, self.session).get_message(
                        user_id, 'error_too_many_downloads'
                    )
                )
                return
            
            # Create worker and queue download
            worker = DownloadWorker(self.localization, self.settings_manager, self.session)
            priority = len(self.active_downloads.get(user_id, {}))  # Lower number = higher priority
            
            await self.download_queue.put((
                priority,
                worker,
                (downloader, url, update, status_message, format_id)
            ))

    async def cleanup(self):
        """Cleanup resources on shutdown"""
        if not self._initialized:
            return
            
        # Stop queue processor
        self._queue_processor_running = False
        if self._queue_processor_task:
            self._queue_processor_task.cancel()
            try:
                await self._queue_processor_task
            except asyncio.CancelledError:
                pass
        
        # Wait for queue to empty
        if self.download_queue:
            try:
                await asyncio.wait_for(self.download_queue.join(), timeout=5.0)
            except Exception:
                pass
        
        # Cancel all active downloads
        if self._downloads_lock:
            async with self._downloads_lock:
                for downloads in self.active_downloads.values():
                    for task in downloads.values():
                        task.cancel()
        
        # Close session
        if self.session:
            await self.session.close()
            
        self._initialized = False

