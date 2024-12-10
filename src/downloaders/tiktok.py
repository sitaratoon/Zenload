import re
import os
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse
import yt_dlp
from .base import BaseDownloader, DownloadError

logger = logging.getLogger(__name__)

class TikTokDownloader(BaseDownloader):
    def platform_id(self) -> str:
        return 'tiktok'

    def __init__(self):
        super().__init__()
        self.cookie_file = Path(__file__).parent.parent.parent / "cookies" / "tiktok.txt"
        self.ydl_opts['cookiefile'] = str(self.cookie_file)

    def _get_ydl_opts(self, format_id: Optional[str] = None) -> Dict:
        """Get yt-dlp options"""
        opts = {
            'format': format_id if format_id else 'best',
            'nooverwrites': True,
            'no_color': True,
            'no_warnings': True,
            'quiet': False,  # Show download progress
            'extract_flat': False,
            'progress_hooks': [self._progress_hook],  # Add progress hook
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
            'extractor_args': {
                'TikTok': {
                    'api_hostname': 'api16-normal-c-useast1a.tiktokv.com'
                }
            }
        }
        if self.cookie_file.exists():
            opts['cookiefile'] = str(self.cookie_file)
        return opts

    def can_handle(self, url: str) -> bool:
        """Check if URL is from TikTok"""
        parsed = urlparse(url)
        logger.info(f"Checking TikTok URL: {url} | Parsed netloc: {parsed.netloc}")
        return bool(
            parsed.netloc and
            any(domain in parsed.netloc.lower() 
                for domain in ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com'])
        )

    def preprocess_url(self, url: str) -> str:
        """Clean and validate TikTok URL"""
        logger.info(f"Preprocessing TikTok URL: {url}")
        if 'vm.tiktok.com' in url:
            logger.info("Detected mobile share URL (vm.tiktok.com)")
            return url
        
        patterns = [
            r'tiktok\.com/@[^/]+/video/(\d+)',
            r'tiktok\.com/t/([^/?]+)',
        ]
        
        for pattern in patterns:
            if match := re.search(pattern, url):
                video_id = match.group(1)
                logger.info(f"Extracted video ID: {video_id} using pattern: {pattern}")
                if video_id.isdigit():
                    processed_url = url.split('?')[0]
                else:
                    processed_url = f'https://www.tiktok.com/t/{video_id}'
                logger.info(f"Processed URL: {processed_url}")
                return processed_url
        
        logger.warning(f"No patterns matched URL: {url}, using as is")
        return url

    async def get_formats(self, url: str) -> List[Dict]:
        """Get available formats for URL"""
        try:
            self.update_progress('status_getting_info', 0)
            processed_url = self.preprocess_url(url)
            logger.info(f"Getting formats for URL: {processed_url}")

            # Configure yt-dlp options
            ydl_opts = self._get_ydl_opts()
            self.update_progress('status_getting_info', 30)

            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    logger.info("Attempting to extract info with yt-dlp")
                    return ydl.extract_info(processed_url, download=False)

            info = await asyncio.to_thread(extract_info)
            self.update_progress('status_getting_info', 60)

            if not info:
                raise DownloadError("Failed to get video information")

            formats = []
            if 'formats' in info:
                seen = set()
                for f in info['formats']:
                    if 'height' in f and f['height']:
                        quality = f"{f['height']}p"
                        if quality not in seen:
                            formats.append({
                                'id': f['format_id'],
                                'quality': quality,
                                'ext': f.get('ext', 'mp4')
                            })
                            seen.add(quality)

            self.update_progress('status_getting_info', 100)
            return sorted(formats, key=lambda x: int(x['quality'][:-1]), reverse=True)

        except Exception as e:
            logger.error(f"Error getting formats: {str(e)}", exc_info=True)
            raise DownloadError(f"Failed to get formats: {str(e)}")

    def _progress_hook(self, d: Dict[str, Any]):
        """Progress hook for yt-dlp"""
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    # Scale progress between 20-90% to leave room for pre/post processing
                    progress = int((downloaded / total) * 70) + 20
                    self.update_progress('status_downloading', progress)
            except Exception as e:
                logger.error(f"Error in progress hook: {e}")

    async def download(self, url: str, format_id: Optional[str] = None) -> Tuple[str, Path]:
        """Download video from URL"""
        try:
            self.update_progress('status_downloading', 10)
            processed_url = self.preprocess_url(url)
            logger.info(f"[TikTok] Downloading from: {processed_url}")

            # Create download directory if not exists
            download_dir = Path(__file__).parent.parent.parent / "downloads"
            download_dir.mkdir(exist_ok=True)
            download_dir = download_dir.resolve()
            logger.info(f"[TikTok] Download directory: {download_dir}")
            
            # Configure yt-dlp options
            ydl_opts = self._get_ydl_opts(format_id)
            temp_filename = f"temp_{self.platform_id()}_{os.urandom(4).hex()}"
            ydl_opts['outtmpl'] = str(download_dir / f"{temp_filename}.%(ext)s")
            
            self.update_progress('status_downloading', 20)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(
                    ydl.extract_info, processed_url, True
                )
                
                if not info:
                    raise DownloadError("Failed to get content information")

                # Find downloaded file
                downloaded_file = None
                for file in download_dir.glob(f"{temp_filename}.*"):
                    if file.is_file():
                        downloaded_file = file
                        break

                if not downloaded_file:
                    raise DownloadError("File was downloaded but not found in the system")
                
                logger.info(f"[TikTok] Downloaded to: {downloaded_file}")
                
                # Format numbers to K/M
                def format_number(num):
                    if not num:
                        return "0"
                    if num >= 1000000:
                        return f"{num/1000000:.1f}M"
                    if num >= 1000:
                        return f"{num/1000:.1f}K"
                    return str(num)

                likes = format_number(info.get('like_count', 0))
                username = info.get('uploader', '').replace('https://www.tiktok.com/@', '').strip()
                
                if info.get('view_count'):
                    views = format_number(info.get('view_count'))
                    metadata = f"TikTok | {views} | {likes}\nby <a href=\"{processed_url}\">{username}</a>"
                else:
                    metadata = f"TikTok | {likes}\nby <a href=\"{processed_url}\">{username}</a>"

                self.update_progress('status_downloading', 100)
                return metadata, downloaded_file
                
        except Exception as e:
            error_msg = str(e)
            if "Private video" in error_msg:
                raise DownloadError("This is a private video")
            elif "Login required" in error_msg:
                raise DownloadError("Authentication required")
            else:
                logger.error(f"[TikTok] Download failed: {error_msg}")
                raise DownloadError(f"Download error: {error_msg}")
