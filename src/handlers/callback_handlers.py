import logging
from telegram import Update
from telegram.ext import ContextTypes
from ..downloaders import DownloaderFactory

logger = logging.getLogger(__name__)

class CallbackHandlers:
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

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries"""
        query = update.callback_query
        await query.answer()
        user_id = update.effective_user.id
        
        try:
            action, value = query.data.split(':')
            
            if action == 'quality':
                await self._handle_quality_callback(query, context, user_id, value)
            elif action == 'settings':
                await self._handle_settings_callback(query, user_id, value)
            elif action == 'set_lang':
                await self._handle_language_callback(update, query, user_id, value)
            elif action == 'set_quality':
                await self._handle_quality_setting_callback(query, user_id, value)
                
        except Exception as e:
            await query.edit_message_text(
                self.get_message(user_id, 'error_occurred')
            )
            logger.error(f"Error in callback handling: {e}")

    async def _handle_quality_callback(self, query, context, user_id: int, quality: str):
        """Handle quality selection for download"""
        url = context.user_data.get('pending_url')
        if not url:
            await query.edit_message_text(
                self.get_message(user_id, 'session_expired')
            )
            return
        
        # Clear stored URL
        context.user_data.clear()
        
        # Get downloader
        downloader = DownloaderFactory.get_downloader(url)
        if not downloader:
            await query.edit_message_text(
                self.get_message(user_id, 'invalid_url')
            )
            return
        
        # Create fake update object for download manager
        class FakeUpdate:
            def __init__(self, effective_user, effective_message):
                self.effective_user = effective_user
                self.effective_message = effective_message

        fake_update = FakeUpdate(
            type('User', (), {'id': user_id})(),
            query.message
        )
        
        # Download with selected format
        await self.download_manager.process_download(
            downloader, 
            url, 
            fake_update,
            query.message, 
            quality
        )

    async def _handle_settings_callback(self, query, user_id: int, setting: str):
        """Handle settings menu navigation"""
        if setting == 'language':
            # Show language selection
            await query.edit_message_text(
                self.get_message(user_id, 'select_language'),
                reply_markup=self.keyboard_builder.build_language_keyboard(user_id)
            )
            
        elif setting == 'quality':
            # Show quality selection
            await query.edit_message_text(
                self.get_message(user_id, 'select_default_quality'),
                reply_markup=self.keyboard_builder.build_quality_keyboard(user_id)
            )
            
        elif setting == 'back':
            # Return to main settings menu
            settings = self.settings_manager.get_settings(user_id)
            quality_display = {
                'ask': self.get_message(user_id, 'ask_every_time'),
                'best': self.get_message(user_id, 'best_available')
            }.get(settings.default_quality, settings.default_quality)
            
            message = self.get_message(
                user_id,
                'settings_menu',
                language=settings.language.upper(),
                quality=quality_display
            )
            await query.edit_message_text(
                message, 
                reply_markup=self.keyboard_builder.build_settings_keyboard(user_id)
            )

    async def _handle_language_callback(self, update, query, user_id: int, language: str):
        """Handle language setting change"""
        settings = self.settings_manager.update_settings(user_id, language=language)
        
        # Send new keyboard with updated language
        await update.effective_message.reply_text(
            self.get_message(user_id, 'welcome'),
            reply_markup=self.keyboard_builder.build_main_keyboard(user_id)
        )
        
        # Update settings menu
        quality_display = {
            'ask': self.get_message(user_id, 'ask_every_time'),
            'best': self.get_message(user_id, 'best_available')
        }.get(settings.default_quality, settings.default_quality)
        
        message = self.get_message(
            user_id,
            'settings_menu',
            language=settings.language.upper(),
            quality=quality_display
        )
        
        await query.edit_message_text(
            message, 
            reply_markup=self.keyboard_builder.build_settings_keyboard(user_id)
        )

    async def _handle_quality_setting_callback(self, query, user_id: int, quality: str):
        """Handle quality setting change"""
        settings = self.settings_manager.update_settings(user_id, default_quality=quality)
        quality_display = {
            'ask': self.get_message(user_id, 'ask_every_time'),
            'best': self.get_message(user_id, 'best_available')
        }.get(settings.default_quality, settings.default_quality)
        
        message = self.get_message(
            user_id,
            'settings_menu',
            language=settings.language.upper(),
            quality=quality_display
        )
        
        await query.edit_message_text(
            message, 
            reply_markup=self.keyboard_builder.build_settings_keyboard(user_id)
        )

