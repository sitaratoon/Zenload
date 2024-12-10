import asyncio
import logging
from pathlib import Path
from .bot import ZenloadBot

def main():
    """Main entry point for the bot"""
    try:
        bot = ZenloadBot()
        bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()
