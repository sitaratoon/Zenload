import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
COOKIES_DIR = BASE_DIR / "cookies"

# Create necessary directories
DOWNLOADS_DIR.mkdir(exist_ok=True)
COOKIES_DIR.mkdir(exist_ok=True)

# Bot Configuration
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Platform specific configurations
YTDLP_OPTIONS = {
    'instagram': {
        'format': 'best',
        'nooverwrites': True,
        'no_color': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'cookiefile': str(COOKIES_DIR / 'instagram.txt'),
        'quiet': True,
        'no_check_certificate': True
    },
    'tiktok': {
        'format': 'best',
        'nooverwrites': True,
        'no_color': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'quiet': True,
        'cookiefile': str(COOKIES_DIR / 'tiktok.txt'),
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        },
        'extractor_args': {'TikTok': {
            'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'
        }},
        'no_check_certificate': True
    },
    'youtube': {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'nooverwrites': True,
        'no_color': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'quiet': True
    }
}

# Logging Configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'standard': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'INFO'
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'bot.log',
            'formatter': 'standard',
            'level': 'INFO'
        }
    },
    'loggers': {
        'src': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True
        },
        'src.downloaders': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False
        },
        'telegram': {
            'level': 'WARNING',
            'propagate': True
        },
        'httpx': {
            'level': 'WARNING',
            'propagate': True
        }
    }
}




