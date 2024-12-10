import logging
from pathlib import Path
from telegram import Update, Message
from telegram.error import BadRequest
from ..downloaders import DownloadError
import asyncio
from functools import partial
import queue
import threading

logger = logging.getLogger(__name__)

class DownloadManager:
    def __init__(self, localization, settings_manager):
        self.localization = localization
        self.settings_manager = settings_manager
        self._current_message = None
        self._current_user_id = None
        self._loop = None
        self._last_status = None
        self._last_progress = None
        self._update_queue = queue.Queue()
        self._update_thread = None

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        language = settings.language
        return self.localization.get(language, key, **kwargs)

    async def update_status(self, message: Message, user_id: int, status_key: str, progress: int):
        """Update status message with current progress"""
        try:
            # Check if status or progress changed
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

    def _process_updates(self):
        """Process status updates in a separate thread"""
        while True:
            try:
                status, progress = self._update_queue.get(timeout=0.5)
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
                    future.result(timeout=5)  # Increased timeout
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing update: {e}")

    def progress_callback(self, status: str, progress: int):
        """Sync callback for progress updates"""
        try:
            self._update_queue.put((status, progress))
        except Exception as e:
            logger.error(f"Error in progress callback: {str(e)}")

    async def process_download(self, 
                             downloader, 
                             url: str, 
                             update: Update, 
                             status_message: Message, 
                             format_id: str = None) -> None:
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
            self._loop = asyncio.get_event_loop()
            
            # Start update processing thread
            self._update_thread = threading.Thread(target=self._process_updates)
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
            logger.info("Sending video to Telegram...")
            
            with open(file_path, 'rb') as video_file:
                await update.effective_message.reply_video(
                    video=video_file,
                    caption=metadata,
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                    pool_timeout=60
                )
            await self.update_status(status_message, user_id, 'status_sending', 100)
            logger.info("Video sent successfully")

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
            # Stop update processing thread
            if self._update_thread and self._update_thread.is_alive():
                self._update_queue.put(("STOP", 0))
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

