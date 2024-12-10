import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from uuid import uuid4

logger = logging.getLogger(__name__)

class InlineHandlers:
    def __init__(self, settings_manager, localization):
        self.settings_manager = settings_manager
        self.localization = localization

    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline query requests"""
        query = update.inline_query.query
        user_id = update.effective_user.id

        if not query:
            return

        # Create an inline result that will post the URL to be processed
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="Download from URL",
                description=f"Process URL: {query}",
                input_message_content=InputTextMessageContent(
                    message_text=f"/zen {query}"
                )
            )
        ]

        await update.inline_query.answer(results)
