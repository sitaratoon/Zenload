import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..downloaders import DownloaderFactory

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, keyboard_builder, settings_manager, download_manager, localization):
        self.keyboard_builder = keyboard_builder
        self.settings_manager = settings_manager
        self.download_manager = download_manager
        self.localization = localization

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        language = settings.language
        return self.localization.get(language, key, **kwargs)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages with URLs in private chats only"""
        if update.effective_chat.type != 'private':
            return
            
        message_text = update.message.text.strip()
        user_id = update.effective_user.id

        # Handle keyboard shortcuts first
        if message_text == self.get_message(user_id, 'btn_settings'):
            from .command_handlers import CommandHandlers
            await CommandHandlers(self.keyboard_builder, self.settings_manager, self.localization).settings_command(update, context)
            return
        elif message_text == self.get_message(user_id, 'btn_help'):
            from .command_handlers import CommandHandlers
            await CommandHandlers(self.keyboard_builder, self.settings_manager, self.localization).help_command(update, context)
            return
        elif message_text == self.get_message(user_id, 'btn_donate'):
            from .command_handlers import CommandHandlers
            await CommandHandlers(self.keyboard_builder, self.settings_manager, self.localization).donate_command(update, context)
            return

        # Process URL
        await self._process_url(message_text, update, context)

    async def _process_url(self, url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process URL from message or command"""
        user_id = update.effective_user.id
        
        # Get downloader for URL
        downloader = DownloaderFactory.get_downloader(url)
        if not downloader:
            message = self.get_message(user_id, 'unsupported_url')
            await update.message.reply_text(message)
            return

        # Send initial status
        status_message = await update.message.reply_text(
            self.get_message(user_id, 'processing')
        )

        try:
            # Get available formats
            formats = await downloader.get_formats(url)
            
            if formats:
                # Store URL in context for callback
                if not context.user_data:
                    context.user_data.clear()
                context.user_data['pending_url'] = url

                # Get user settings
                settings = self.settings_manager.get_settings(user_id)
                
                # If default quality is set and not 'ask', use it
                if settings.default_quality != 'ask':
                    await self.download_manager.process_download(
                        downloader, 
                        url, 
                        update, 
                        status_message, 
                        settings.default_quality
                    )
                    return
                
                # Show quality selection keyboard
                await status_message.edit_text(
                    self.get_message(user_id, 'select_quality'),
                    reply_markup=self.keyboard_builder.build_format_selection_keyboard(user_id, formats)
                )
            else:
                # If no formats available, download with default settings
                await self.download_manager.process_download(downloader, url, update, status_message)

        except Exception as e:
            await update.message.reply_text(
                self.get_message(user_id, 'error_occurred')
            )
            logger.error(f"Unexpected error processing {url}: {e}")
            await status_message.delete()

