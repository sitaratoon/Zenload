import logging
import logging.config
from pathlib import Path
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, PreCheckoutQueryHandler, filters
import signal
import asyncio
import sys

from .config import TOKEN, LOGGING_CONFIG, BASE_DIR
from .database import UserSettingsManager, UserActivityLogger
from .locales import Localization
from .utils import KeyboardBuilder, DownloadManager
from .handlers import CommandHandlers, MessageHandlers, CallbackHandlers, PaymentHandlers

# Configure logging
logging.config.dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

class ZenloadBot:
    def __init__(self):
        # Initialize core components
        self.application = Application.builder().token(TOKEN).build()
        self.settings_manager = UserSettingsManager()
        self.localization = Localization()
        self.activity_logger = UserActivityLogger(self.settings_manager.db)
        
        # Initialize utility classes
        self.keyboard_builder = KeyboardBuilder(
            self.localization,
            self.settings_manager
        )
        self.download_manager = DownloadManager(
            self.localization,
            self.settings_manager,
            activity_logger=self.activity_logger
        )
        
        # Initialize handlers
        self.command_handlers = CommandHandlers(
            self.keyboard_builder,
            self.settings_manager,
            self.localization
        )
        self.message_handlers = MessageHandlers(
            self.keyboard_builder,
            self.settings_manager,
            self.download_manager,
            self.localization,
            activity_logger=self.activity_logger
        )
        self.callback_handlers = CallbackHandlers(
            self.keyboard_builder,
            self.settings_manager,
            self.download_manager,
            self.localization,
            activity_logger=self.activity_logger
        )
        self.payment_handlers = PaymentHandlers(
            self.localization,
            self.settings_manager
        )
        
        self._setup_handlers()
        self._stopping = False

    def _setup_handlers(self):
        """Setup bot command and message handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.command_handlers.start_command))
        self.application.add_handler(CommandHandler("zen", self.command_handlers.zen_command))
        self.application.add_handler(CommandHandler("help", self.command_handlers.help_command))
        self.application.add_handler(CommandHandler("settings", self.command_handlers.settings_command))
        self.application.add_handler(CommandHandler("donate", self.command_handlers.donate_command))
        self.application.add_handler(CommandHandler("paysupport", self.command_handlers.paysupport_command))
        
        # Payment handlers
        self.application.add_handler(PreCheckoutQueryHandler(self.payment_handlers.pre_checkout_callback))
        
        # Message handlers for private chats
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
            self.message_handlers.handle_message
        ))
        
        # Message handlers for group chats (with bot mention)
        self.application.add_handler(MessageHandler(
            (filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & filters.Entity("mention")),
            self.message_handlers.handle_message
        ))
        
        # Callback query handler
        self.application.add_handler(CallbackQueryHandler(self.callback_handlers.handle_callback))

    async def stop(self):
        """Stop the bot gracefully"""
        if self._stopping:
            return
        
        self._stopping = True
        logger.info("Stopping bot...")
        
        try:
            # Ensure we're in the right event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Stop accepting new updates
            if self.application.updater:
                await self.application.updater.stop()
            
            # Cleanup download manager with timeout
            try:
                await asyncio.wait_for(self.download_manager.cleanup(), timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning("Download manager cleanup timed out")
            except Exception as e:
                logger.error(f"Error during download manager cleanup: {e}")
            
            # Stop application
            if self.application.running:
                try:
                    await asyncio.wait_for(self.application.stop(), timeout=5.0)
                    await asyncio.wait_for(self.application.shutdown(), timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Application shutdown timed out")
            
            logger.info("Bot stopped successfully")
        except Exception as e:
            logger.error(f"Error stopping bot: {e}", exc_info=True)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        if self._stopping:
            logger.info("Forced shutdown")
            sys.exit(1)
        
        logger.info(f"Received signal {signum}")
        loop = asyncio.get_event_loop()
        loop.create_task(self.stop())

    def run(self):
        """Start the bot"""
        logger.info("Starting Zenload bot...")
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        try:
            self.application.run_polling(drop_pending_updates=True)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise
        finally:
            # Ensure cleanup is performed
            if not self._stopping:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.stop())


