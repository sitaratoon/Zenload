import logging
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, keyboard_builder, settings_manager, localization):
        self.keyboard_builder = keyboard_builder
        self.settings_manager = settings_manager
        self.localization = localization

    def get_message(self, user_id: int, key: str, **kwargs) -> str:
        """Get localized message"""
        settings = self.settings_manager.get_settings(user_id)
        language = settings.language
        return self.localization.get(language, key, **kwargs)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        chat_type = update.effective_chat.type
        
        if chat_type in ['group', 'supergroup']:
            message = self.get_message(user_id, 'group_welcome')
            await update.message.reply_text(message)
        else:
            message = self.get_message(user_id, 'welcome')
            await update.message.reply_text(
                message,
                reply_markup=self.keyboard_builder.build_main_keyboard(user_id)
            )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = self.get_message(update.effective_user.id, 'help')
        await update.message.reply_text(message)

    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
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
        
        await update.message.reply_text(
            message,
            reply_markup=self.keyboard_builder.build_settings_keyboard(user_id)
        )

    async def donate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /donate command"""
        user_id = update.effective_user.id

        # Create invoice for Stars payment
        title = self.get_message(user_id, 'invoice_title')
        description = self.get_message(user_id, 'invoice_description')
        payload = "donate_stars"
        currency = "XTR"  # Correct Telegram Stars currency code
        prices = [
            LabeledPrice(label=self.get_message(user_id, 'price_label'), amount=100)  # 100 Stars
        ] 

        # Send invoice with single price option
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title=title,
            description=description,
            payload=payload,
            provider_token="",  # Empty for Stars payments
            currency=currency,
            prices=prices
        )

    async def paysupport_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /paysupport command for payment support"""
        user_id = update.effective_user.id
        await update.message.reply_text(self.get_message(user_id, 'payment_support'))

    async def zen_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /zen command"""
        user_id = update.effective_user.id
        
        # Extract URL from command arguments
        if not context.args:
            await update.message.reply_text(
                self.get_message(user_id, 'missing_url')
            )
            return
        
        url = context.args[0]
        
        # Import MessageHandlers here to avoid circular imports
        from .message_handlers import MessageHandlers
        from ..utils import DownloadManager
        
        # Create message handler instance
        message_handler = MessageHandlers(
            self.keyboard_builder,
            self.settings_manager,
            DownloadManager(
                self.localization,
                self.settings_manager
            ),
            self.localization
        )
        
        # Process URL using message handler
        await message_handler._process_url(url, update, context)


