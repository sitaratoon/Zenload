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
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)

class DownloadWorker:
    """Worker class to handle individual downloads"""
    def __init__(self, localization, settings_manager):
        self.localization = localization
        self.settings_manager = settings_manager
        self._status_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._current_message: Optional[Message] = None
        self._current_user_id: Optional[int] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_status: Optional[str] = None
        self._last_progress: Optional[int] = None
        self._update_thread: Optional[threading.Thread] = None

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        language = settings.language
        return self.localization.get(language, key, **kwargs)

    async def update_status(self, message: Message, user_id: int, status_key: str, progress: int):
        """Update status message with current progress"""
        try:
            new_text = self.get_message(user_id, status_key, progress=progress)
            if new_text == self._last_status and progress == self._last_progress:
                return

            await message.edit_text(new_text)
            self._last_status = new_text
            self._last_progress = progress

        except BadRequest as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error updating status: {e}")
        except Exception as e:
            logger.error(f"Error updating status: {e}")

    def _process_status_updates(self):
        """Process status updates in a separate thread"""
        while not self._stop_event.is_set():
            try:
                status, progress = self._status_queue.get(timeout=0.1)
                if status == "STOP":
                    break

                if self._current_message and self._current_user_id and self._loop:
                    future = asyncio.run_coroutine_threadsafe(
                        self.update_status(
                            self._current_message,
                            self._current_user_id,
                            status,
                            progress
                        ),
                        self._loop
                    )
                    try:
                        future.result(timeout=3)
                    except asyncio.TimeoutError:
                        logger.warning(f"Status update timed out: {status} {progress}%")
                        self._clear_status_queue()
                    except Exception as e:
                        logger.warning(f"Status update failed: {e}")

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing status update: {e}")

    def _clear_status_queue(self):
        """Clear the status update queue"""
        while not self._status_queue.empty():
            try:
                self._status_queue.get_nowait()
            except queue.Empty:
                break

    def progress_callback(self, status: str, progress: int):
        """Sync callback for progress updates"""
        try:
            self._status_queue.put((status, progress))
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
            self._loop = asyncio.get_running_loop()
            self._stop_event.clear()
            
            # Start status update thread
            self._update_thread = threading.Thread(target=self._process_status_updates)
            self._update_thread.start()
            
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
            # Stop status update thread
            self._stop_event.set()
            if self._update_thread and self._update_thread.is_alive():
                self._status_queue.put(("STOP", 0))
                self._update_thread.join(timeout=1)

            # Clear state
            self._current_message = None
            self._current_user_id = None
            self._loop = None
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
    """Thread-safe download manager with connection pooling and rate limiting"""
    def __init__(self, localization, settings_manager, max_concurrent_downloads=10, max_downloads_per_user=2):
        self.localization = localization
        self.settings_manager = settings_manager
        self.max_concurrent_downloads = max_concurrent_downloads
        self.max_downloads_per_user = max_downloads_per_user
        
        # Connection pool for external requests
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(limit=max_concurrent_downloads)
        )
        
        # Thread pool for download workers
        self.thread_pool = ThreadPoolExecutor(max_workers=max_concurrent_downloads)
        
        # Active downloads tracking
        self.active_downloads: Dict[int, Dict[str, DownloadWorker]] = {}
        self._downloads_lock = threading.Lock()
        
        # Rate limiting
        self.rate_limit = 5  # requests per second
        self.rate_limit_period = 1.0  # seconds
        self._last_request_times = []
        self._rate_limit_lock = threading.Lock()

    async def _check_rate_limit(self):
        """Check and enforce rate limiting"""
        current_time = time.time()
        with self._rate_limit_lock:
            # Remove old requests
            self._last_request_times = [t for t in self._last_request_times 
                                      if current_time - t <= self.rate_limit_period]
            
            if len(self._last_request_times) >= self.rate_limit:
                # Wait if rate limit exceeded
                oldest_time = self._last_request_times[0]
                wait_time = self.rate_limit_period - (current_time - oldest_time)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            self._last_request_times.append(current_time)

    async def process_download(self, downloader, url: str, update: Update, status_message: Message, format_id: str = None) -> None:
        """Process download request with rate limiting and connection pooling"""
        user_id = update.effective_user.id
        
        # Check rate limit
        await self._check_rate_limit()
        
        # Create new worker for this download
        worker = DownloadWorker(self.localization, self.settings_manager)
        
        with self._downloads_lock:
            # Initialize user's downloads dict if not exists
            if user_id not in self.active_downloads:
                self.active_downloads[user_id] = {}
            
            # Clean up completed downloads for this user
            self.active_downloads[user_id] = {
                url: w for url, w in self.active_downloads[user_id].items()
                if not w._stop_event.is_set()
            }
            
            # Check user's concurrent downloads limit
            if len(self.active_downloads[user_id]) >= self.max_downloads_per_user:
                await status_message.edit_text(
                    worker.get_message(user_id, 'error_too_many_downloads')
                )
                return
            
            # Add to active downloads
            self.active_downloads[user_id][url] = worker
        
        try:
            # Process download
            await worker.process_download(downloader, url, update, status_message, format_id)
        finally:
            # Cleanup
            with self._downloads_lock:
                if user_id in self.active_downloads and url in self.active_downloads[user_id]:
                    del self.active_downloads[user_id][url]
                    if not self.active_downloads[user_id]:
                        del self.active_downloads[user_id]

    async def cleanup(self):
        """Cleanup resources on shutdown"""
        # Stop all active downloads
        with self._downloads_lock:
            for user_downloads in self.active_downloads.values():
                for worker in user_downloads.values():
                    worker._stop_event.set()
        
        # Close connection pool
        await self.session.close()
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=True)
