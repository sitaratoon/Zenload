import re
import os
from urllib.parse import urlparse, parse_qs
from .base import BaseDownloader


class YouTubeDownloader(BaseDownloader):
    def platform_id(self) -> str:
        return 'youtube'

    def can_handle(self, url: str) -> bool:
        """Check if URL is from YouTube"""
        parsed = urlparse(url)
        return bool(
            parsed.netloc and
            any(domain in parsed.netloc.lower() 
                for domain in ['youtube.com', 'www.youtube.com', 'youtu.be'])
        )

    def preprocess_url(self, url: str) -> str:
        """Clean and validate YouTube URL"""
        parsed = urlparse(url)
        
        # Handle youtu.be URLs
        if 'youtu.be' in parsed.netloc:
            video_id = parsed.path.lstrip('/')
            return f'https://www.youtube.com/watch?v={video_id}'
            
        # Handle youtube.com URLs
        if 'youtube.com' in parsed.netloc:
            # Handle various YouTube URL formats
            if '/watch' in parsed.path:
                # Regular video URL
                return url
            elif '/shorts/' in parsed.path:
                # YouTube Shorts
                video_id = parsed.path.split('/shorts/')[1]
                return f'https://www.youtube.com/watch?v={video_id}'
            elif '/playlist' in parsed.path:
                # Return as is - yt-dlp handles playlists
                return url
                
        return url

    def get_title(self, info: dict) -> str:
        """Get meaningful title for YouTube content"""
        if title := info.get('title'):
            return title
            
        # Fallback to video ID or random
        video_id = info.get('id', '')
        return f"youtube_video_{video_id or os.urandom(4).hex()}"
