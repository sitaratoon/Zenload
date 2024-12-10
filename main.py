import logging
from src.bot import ZenloadBot

if __name__ == "__main__":
    try:
        # Initialize and run the bot
        bot = ZenloadBot()
        bot.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        raise
