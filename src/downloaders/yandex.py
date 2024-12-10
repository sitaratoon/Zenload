import os
import re
import logging
from pathlib import Path
from typing import Tuple, Dict, List
from yandex_music import Client

from .base import BaseDownloader, DownloadError
from ..config import DOWNLOADS_DIR

logger = logging.getLogger(__name__)

class YandexMusicDownloader(BaseDownloader):
    """Downloader for Yandex Music"""

    def __init__(self):
        super().__init__()
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initialize Yandex Music client"""
        token = os.getenv('YANDEX_MUSIC_TOKEN')
        if not token:
            logger.warning("YANDEX_MUSIC_TOKEN not found in environment variables")
            return
        
        try:
            self.client = Client(token).init()
            logger.info("Yandex Music client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Yandex Music client: {e}")
            self.client = None

    def platform_id(self) -> str:
        return "yandex_music"

    def can_handle(self, url: str) -> bool:
        """Check if URL is from Yandex Music"""
        patterns = [
            r'music\.yandex\.[a-z]+/album/(\d+)/track/(\d+)',
            r'music\.yandex\.[a-z]+/track/(\d+)',
        ]
        return any(re.search(pattern, url) for pattern in patterns)

    def _extract_track_id(self, url: str) -> str:
        """Extract track ID from URL"""
        # Try album/track pattern first
        match = re.search(r'album/(\d+)/track/(\d+)', url)
        if match:
            return f"{match.group(2)}:{match.group(1)}"
        
        # Try direct track pattern
        match = re.search(r'track/(\d+)', url)
        if match:
            return match.group(1)
        
        raise DownloadError("Could not extract track ID from URL")

    async def get_formats(self, url: str) -> List[Dict]:
        """Get available formats - for Yandex Music it's just MP3"""
        return [{
            'id': 'mp3',
            'quality': 'MP3 320kbps',
            'ext': 'mp3'
        }]

    async def download(self, url: str, format_id: str = None) -> Tuple[str, Path]:
        """Download track from Yandex Music"""
        if not self.client:
            raise DownloadError("Yandex Music client not initialized. Check your token.")

        try:
            self.update_progress('status_downloading', 0)
            track_id = self._extract_track_id(url)
            logger.info(f"Downloading track ID: {track_id}")

            # Get track info
            track = self.client.tracks([track_id])[0]
            if not track:
                raise DownloadError("Track not found")

            # Get download info
            self.update_progress('status_downloading', 20)
            download_info = track.get_download_info()
            if not download_info:
                raise DownloadError("No download info available")

            # Find best quality
            best_info = max(download_info, key=lambda x: x.bitrate_in_kbps)
            
            # Get download link
            self.update_progress('status_downloading', 40)
            download_url = best_info.get_direct_link()
            
            # Prepare filename
            title = self._prepare_filename(track.title)
            artists = ", ".join(artist.name for artist in track.artists)
            filename = f"{artists} - {title}.mp3"
            file_path = DOWNLOADS_DIR / filename

            # Download file
            self.update_progress('status_downloading', 60)
            track.download(file_path)
            self.update_progress('status_downloading', 100)

            # Format metadata
            metadata = []
            metadata.append(f"{track.title}")
            if artists:
                metadata.append(f"By: {artists}")
            if track.albums and track.albums[0].title:
                metadata.append(f"Album: {track.albums[0].title}")
            duration_mins = track.duration_ms // 60000
            duration_secs = (track.duration_ms % 60000) // 1000
            metadata.append(f"Length: {duration_mins}:{duration_secs:02d}")

            return " | ".join(metadata), file_path

        except Exception as e:
            logger.error(f"Error downloading from Yandex Music: {str(e)}", exc_info=True)
            raise DownloadError(f"Download error: {str(e)}")
