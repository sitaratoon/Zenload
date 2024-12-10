import os
import re
import json
import asyncio
import logging
import http.cookiejar
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

    def _load_cookies(self) -> Dict[str, str]:
        """Load cookies from file"""
        if not self.cookie_file.exists():
            logger.warning(f"Cookie file not found: {self.cookie_file}")
            return {}

        cookiejar = http.cookiejar.MozillaCookieJar(str(self.cookie_file))
        try:
            cookiejar.load(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            logger.error(f"Error loading cookies: {str(e)}")
            return {}

        cookies = {}
        for cookie in cookiejar:
            if cookie.domain.endswith('instagram.com'):
                cookies[cookie.name] = cookie.value
        return cookies

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
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '129477',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.instagram.com'
        }
        cookies = self._load_cookies()
        response = await asyncio.to_thread(requests.get, url, headers=headers, cookies=cookies, allow_redirects=False)
        
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
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }
        if self.cookie_file.exists():
            opts['cookiefile'] = str(self.cookie_file)
        return opts

    async def _try_api_download(self, url: str) -> Dict:
        """Try downloading using Instagram API with auth"""
        cookies = self._load_cookies()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-IG-App-ID': '936619743392459',
            'X-ASBD-ID': '129477',
            'X-IG-WWW-Claim': '0',
            'X-Requested-With': 'XMLHttpRequest',
            'Origin': 'https://www.instagram.com',
            'Referer': url
        }

        api_url = f'{url}?__a=1&__d=dis'
        response = await asyncio.to_thread(requests.get, api_url, headers=headers, cookies=cookies)
        
        if response.status_code == 200:
            try:
                data = response.json()
                if 'items' in data and len(data['items']) > 0:
                    return data['items'][0]
            except:
                pass
        return None

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
            
            # First try standard yt-dlp approach
            try:
                ydl_opts = self._get_ydl_opts()
                ydl_opts.update({
                    'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
                })
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(
                        ydl.extract_info, str(resolved_url), download=False
                    )
                    if info and 'formats' in info:
                        formats = []
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
                        if formats:
                            logger.info("[Instagram] Got formats using standard approach")
                            return sorted(formats, key=lambda x: int(x['quality'][:-1]), reverse=True)
            except Exception as e:
                logger.info(f"[Instagram] Standard approach failed: {e}, trying API approach")

            # If standard approach failed, try API approach
            info = await self._try_api_download(resolved_url)
            if info:
                formats = []
                if 'video_versions' in info:
                    seen = set()
                    for v in info['video_versions']:
                        if not v.get('height'):
                            continue
                        quality = f"{v['height']}p"
                        if quality not in seen:
                            formats.append({
                                'id': str(v.get('id', '')),
                                'quality': quality,
                                'ext': 'mp4'
                            })
                            seen.add(quality)
                    logger.info("[Instagram] Got formats using API approach")
                    return sorted(formats, key=lambda x: int(x['quality'][:-1]), reverse=True)

            raise DownloadError("Не удалось получить информацию о медиафайле")
                
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
            
            # First try standard yt-dlp approach
            try:
                ydl_opts = self._get_ydl_opts(format_id)
                ydl_opts.update({
                    'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
                })
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    self.update_progress('status_downloading', 20)
                    info = await asyncio.to_thread(
                        ydl.extract_info, str(resolved_url), download=True
                    )
                    if info:
                        # Get downloaded file path and verify it exists
                        filename = ydl.prepare_filename(info)
                        file_path = Path(filename).resolve()
                        if file_path.exists():
                            logger.info("[Instagram] Downloaded using standard approach")
                            return self._prepare_metadata(info, resolved_url), file_path
            except Exception as e:
                logger.info(f"[Instagram] Standard download failed: {e}, trying API approach")

            # If standard approach failed, try API approach
            info = await self._try_api_download(resolved_url)
            if info and 'video_versions' in info:
                # Get the best quality video URL
                video_url = sorted(info['video_versions'], key=lambda x: x.get('height', 0), reverse=True)[0]['url']
                
                # Download the video
                self.update_progress('status_downloading', 50)
                response = await asyncio.to_thread(requests.get, video_url)
                if response.status_code == 200:
                    file_path = download_dir / f"{info.get('id', 'video')}.mp4"
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                    logger.info("[Instagram] Downloaded using API approach")
                    return self._prepare_metadata(info, resolved_url), file_path

            raise DownloadError("Не удалось загрузить медиафайл")
                
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

    def _prepare_metadata(self, info: Dict, url: str) -> str:
        """Prepare metadata string from info"""
        def format_number(num):
            if not num:
                return "0"
            if num >= 1000000:
                return f"{num/1000000:.1f}M"
            if num >= 1000:
                return f"{num/1000:.1f}K"
            return str(num)

        likes = format_number(info.get('like_count', 0))
        username = info.get('user', {}).get('username', '') or info.get('uploader', '').replace('https://www.instagram.com/', '').strip()

        if info.get('view_count') or info.get('play_count'):
            views = format_number(info.get('view_count', 0) or info.get('play_count', 0))
            return f"Instagram | {views} | {likes}\nby <a href=\"{url}\">{username}</a>"
        else:
            return f"Instagram | {likes}\nby <a href=\"{url}\">{username}</a>"

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
