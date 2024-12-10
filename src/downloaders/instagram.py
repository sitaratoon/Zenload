import os
import re
import json
import asyncio
import logging
from pathlib import Path
from time import sleep
from typing import Optional, Tuple, List, Dict, Any
import requests
import yt_dlp
from urllib.parse import urlparse, urlunparse
from .base import BaseDownloader, DownloadError

logger = logging.getLogger(__name__)

class RateLimitError(DownloadError):
    """Custom exception for rate limit errors"""
    pass

class InstagramDownloader(BaseDownloader):
    def __init__(self):
        super().__init__()
        self.cookie_file = Path(__file__).parent.parent.parent / "cookies" / "instagram.txt"
        self.last_request_time = 0
        self.min_request_interval = 2  # Minimum seconds between requests
        self.max_retries = 3

    async def _make_request(self, url: str, retry_count: int = 0) -> requests.Response:
        """Make a rate-limited request with retry logic"""
        if retry_count >= self.max_retries:
            raise RateLimitError("Превышен лимит запросов к Instagram. Пожалуйста, подождите несколько минут и попробуйте снова.")

        # Implement rate limiting
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            await asyncio.sleep(self.min_request_interval - time_since_last)

        self.last_request_time = asyncio.get_event_loop().time()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = await asyncio.to_thread(requests.get, url, headers=headers, allow_redirects=False)
        
        if response.status_code == 429:
            # Exponential backoff
            wait_time = (2 ** retry_count) * 5  # 5, 10, 20 seconds
            logger.warning(f"[Instagram] Rate limited, waiting {wait_time} seconds before retry")
            await asyncio.sleep(wait_time)
            return await self._make_request(url, retry_count + 1)

        # Handle redirect manually to get proper final URL
        if response.status_code in [301, 302, 303, 307, 308]:
            redirect_url = response.headers['location']
            # Handle relative URLs
            if redirect_url.startswith('/'):
                parsed = urlparse(url)
                redirect_url = f"{parsed.scheme}://{parsed.netloc}{redirect_url}"
            # Log the redirect chain
            logger.info(f"[Instagram] Following redirect: {url} -> {redirect_url}")
            return await self._make_request(redirect_url, retry_count)
        
        return response

    def platform_id(self) -> str:
        """Return platform identifier"""
        return 'instagram'

    def can_handle(self, url: str) -> bool:
        """Check if URL is from Instagram"""
        return any(x in url for x in ["instagram.com", "instagr.am", "/share/"])

    def _get_ydl_opts(self, format_id: Optional[str] = None) -> Dict:
        """Get yt-dlp options"""
        opts = {
            'format': format_id if format_id else 'best',
            'nooverwrites': True,
            'no_color': True,
            'no_warnings': True,
            'quiet': False,  # Show download progress
            'progress_hooks': [self._progress_hook],  # Add progress hook
            'extractor_args': {
                'instagram': {
                    'api': ['https://i.instagram.com/api/v1'],
                    'fatal_csrf': False
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'X-IG-App-ID': '936619743392459'
            }
        }
        if self.cookie_file.exists():
            opts['cookiefile'] = str(self.cookie_file)
        return opts

    async def _resolve_share_url(self, url: str) -> str:
        """Resolve Instagram share URL to actual post URL"""
        if '/share/' not in url:
            return url

        logger.info(f"[Instagram] Processing share URL: {url}")
        try:
            self.update_progress('status_getting_info', 10)
            response = await self._make_request(url)
            if response.status_code != 200:
                raise DownloadError(f"Ошибка HTTP {response.status_code}")
            
            final_url = str(response.url)
            # Strip URL parameters
            if '?' in final_url:
                final_url = final_url.split('?')[0]
            final_url = final_url.rstrip('/')
            logger.info(f"[Instagram] Resolved to: {final_url}")
            self.update_progress('status_getting_info', 20)
            return final_url

        except RateLimitError as e:
            logger.error(f"[Instagram] Rate limit error: {e}")
            raise
        except Exception as e:
            logger.error(f"[Instagram] Share URL resolution failed: {e}")
            if "429" in str(e):
                raise DownloadError("Превышен лимит запросов к Instagram. Пожалуйста, подождите несколько минут и попробуйте снова.")
            raise DownloadError(f"Ошибка при обработке share-ссылки: {str(e)}")

    async def get_formats(self, url: str) -> List[Dict]:
        """Get available formats for URL"""
        try:
            # Resolve share URL if needed
            self.update_progress('status_getting_info', 0)
            resolved_url = await self._resolve_share_url(url)
            logger.info(f"[Instagram] Getting formats for: {resolved_url}")

            self.update_progress('status_getting_info', 30)
            # Create download directory if not exists
            download_dir = Path(__file__).parent.parent.parent / "downloads"
            download_dir.mkdir(exist_ok=True)
            
            ydl_opts = self._get_ydl_opts()
            ydl_opts.update({
                'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract media ID from URL
                media_id = re.search(r'/reel/([^/?]+)', resolved_url).group(1)
                # Try direct API endpoint first
                api_url = f'https://i.instagram.com/api/v1/media/{media_id}/info/'
                
                # Add custom extractor args for this URL
                ydl_opts['extractor_args']['instagram'].update({
                    'media_id': [media_id]
                })
                info = await asyncio.to_thread(ydl.extract_info,
                    api_url, download=False
                )
                self.update_progress('status_getting_info', 70)
                
                if not info:
                    raise DownloadError("Не удалось получить информацию о медиафайле")

                formats = []
                if 'formats' in info:
                    seen = set()
                    for f in info['formats']:
                        if not f.get('height'):
                            continue
                        
                        quality = f"{f['height']}p"
                        if quality not in seen:
                            formats.append({
                                'id': f['format_id'],
                                'quality': quality,
                                'ext': f['ext']
                            })
                            seen.add(quality)
                
                self.update_progress('status_getting_info', 100)
                logger.info(f"[Instagram] Available formats: {formats}")
                return sorted(formats, key=lambda x: int(x['quality'][:-1]), reverse=True)
                
        except RateLimitError as e:
            logger.error(f"[Instagram] Rate limit error: {e}")
            raise
        except Exception as e:
            logger.error(f"[Instagram] Format extraction failed: {e}")
            if "429" in str(e):
                raise DownloadError("Превышен лимит запросов к Instagram. Пожалуйста, подождите несколько минут и попробуйте снова.")
            raise DownloadError(f"Ошибка при получении форматов: {str(e)}")

    async def download(self, url: str, format_id: Optional[str] = None) -> Tuple[str, Path]:
        """Download video from URL"""
        try:
            # Resolve share URL if needed
            self.update_progress('status_downloading', 0)
            resolved_url = await self._resolve_share_url(url)
            logger.info(f"[Instagram] Downloading from: {resolved_url}")

            # Create download directory if not exists
            download_dir = Path(__file__).parent.parent.parent / "downloads"
            download_dir.mkdir(exist_ok=True)
            download_dir = download_dir.resolve()  # Get absolute path
            logger.info(f"[Instagram] Download directory: {download_dir}")
            
            # Configure yt-dlp options
            ydl_opts = self._get_ydl_opts(format_id)
            ydl_opts.update({
                'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
            })
            
            self.update_progress('status_downloading', 10)
            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.update_progress('status_downloading', 20)
                info = await asyncio.to_thread(
                    # Pass the resolved URL directly to yt-dlp
                    ydl.extract_info, str(resolved_url), download=True
                )
                
                if not info:
                    raise DownloadError("Не удалось загрузить медиафайл")

                # Get downloaded file path and verify it exists
                filename = ydl.prepare_filename(info)
                file_path = Path(filename).resolve()
                logger.info(f"[Instagram] Looking for file at: {file_path}")
                
                if not file_path.exists():
                    raise DownloadError("Файл был загружен, но не найден на диске")
                
                logger.info(f"[Instagram] Downloaded to: {file_path}")
                
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
                username = info.get('uploader', '').replace('https://www.instagram.com/', '').strip()

                # Instagram часто не отдает просмотры, поэтому показываем их только если они есть
                if info.get('view_count'):
                    views = format_number(info.get('view_count'))
                    metadata = f"Instagram | {views} | {likes}\nby <a href=\"{resolved_url}\">{username}</a>"
                else:
                    metadata = f"Instagram | {likes}\nby <a href=\"{resolved_url}\">{username}</a>"

                self.update_progress('status_downloading', 100)
                return metadata, file_path
                
        except RateLimitError as e:
            logger.error(f"[Instagram] Rate limit error: {e}")
            raise
        except Exception as e:
            error_msg = str(e)
            if "Private video" in error_msg or "Private profile" in error_msg:
                raise DownloadError("Это приватный контент")
            elif "Login required" in error_msg or "Cookie" in error_msg:
                raise DownloadError("Требуется авторизация")
            elif "429" in error_msg:
                raise DownloadError("Превышен лимит запросов к Instagram. Пожалуйста, подождите несколько минут и попробуйте снова.")
            else:
                logger.error(f"[Instagram] Download failed: {error_msg}")
                raise DownloadError(f"Ошибка загрузки: {error_msg}")

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





