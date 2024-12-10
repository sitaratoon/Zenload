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
TOKEN = "7920776459:AAGMagjuo8guK4XVVTzIWR2NM0u_Q95B8LM"

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
        'quiet': True
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

