import re
from urllib.parse import urlparse
from .base import BaseDownloader


class TikTokDownloader(BaseDownloader):
    def platform_id(self) -> str:
        return 'tiktok'

    def can_handle(self, url: str) -> bool:
        """Check if URL is from TikTok"""
        parsed = urlparse(url)
        return bool(
            parsed.netloc and
            any(domain in parsed.netloc.lower() 
                for domain in ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com'])
        )

    def preprocess_url(self, url: str) -> str:
        """Clean and validate TikTok URL"""
        # Handle mobile share URLs
        if 'vm.tiktok.com' in url:
            return url  # yt-dlp handles URL redirection automatically
        
        # Extract video ID from URL
        patterns = [
            r'tiktok\.com/@[^/]+/video/(\d+)',
            r'tiktok\.com/t/([^/?]+)',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, url):
                video_id = match.group(1)
                if video_id.isdigit():
                    return f'https://www.tiktok.com/video/{video_id}'
                return f'https://www.tiktok.com/t/{video_id}'
        
        return url

    def get_title(self, info: dict) -> str:
        """Get meaningful title for TikTok content"""
        if title := info.get('title'):
            return title
        
        # Construct title from author and ID
        author = info.get('uploader', '')
        video_id = info.get('id', '')
        
        if author and video_id:
            return f"{author}_video_{video_id}"
            
        return f"tiktok_video_{video_id or os.urandom(4).hex()}"
