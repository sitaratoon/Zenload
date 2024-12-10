# Zenload

High-performance Telegram bot for downloading videos from social media platforms.

## Features

- Fast and efficient video downloads
- Support for Instagram, TikTok, YouTube
- Automatic format optimization
- Clean and intuitive interface
- Robust error handling

## Installation

```bash
git clone https://github.com/yourusername/zenload.git
cd zenload
pip install -r requirements.txt
```

Optional: Add cookies/instagram.txt for enhanced Instagram functionality

## Usage

1. Find @Zenload_bot on Telegram
2. Send a video URL from supported platforms
3. Receive the downloaded video

## Project Structure

```
zenload/
├── src/
│   ├── bot.py          # Bot core
│   ├── config.py       # Configuration
│   ├── downloaders/    # Platform-specific downloaders
│   ├── handlers/       # Telegram handlers
│   └── utils/         # Utility functions
├── downloads/         # Temporary downloads
├── cookies/          # Platform cookies
└── main.py          # Entry point
```

## Supported Platforms

- Instagram (Reels, Posts)
- TikTok

## Technical Details

- Asynchronous download processing
- Memory-efficient file handling
- Automatic cleanup of temporary files
- Rate limiting and spam protection
- Comprehensive error handling

## License

MIT License
