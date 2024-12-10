import os
import re
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
import requests
import yt_dlp
from urllib.parse import urlparse, urlunparse
from .base import BaseDownloader, DownloadError

logger = logging.getLogger(__name__)

class InstagramDownloader(BaseDownloader):
    def __init__(self):
        super().__init__()
        self.cookie_file = Path(__file__).parent.parent.parent / "cookies" / "instagram.txt"

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
            'extract_flat': False,
            'progress_hooks': [self._progress_hook],  # Add progress hook
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'X-IG-App-ID': '936619743392459'
            }
        }
        return opts

    async def _resolve_share_url(self, url: str) -> str:
        """Resolve Instagram share URL to actual post URL"""
        if '/share/' not in url:
            return url

        logger.info(f"[Instagram] Processing share URL: {url}")
        try:
            self.update_progress('status_getting_info', 10)
            response = await asyncio.to_thread(requests.get, url, allow_redirects=True)
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

        except Exception as e:
            logger.error(f"[Instagram] Share URL resolution failed: {e}")
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
            
            # Configure yt-dlp options with output template
            ydl_opts = self._get_ydl_opts()
            ydl_opts.update({
                'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
            })
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.update_progress('status_getting_info', 50)
                info = await asyncio.to_thread(
                    ydl.extract_info, resolved_url, True
                )
                self.update_progress('status_getting_info', 70)
                
                if not info:
                    raise DownloadError("Не удалось получить информацию о видео")

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
                
        except Exception as e:
            logger.error(f"[Instagram] Format extraction failed: {e}")
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
                    ydl.extract_info, resolved_url, True  # Changed to True to force download
                )
                
                if not info:
                    raise DownloadError("Не удалось загрузить видео")

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
                
        except Exception as e:
            error_msg = str(e)
            if "Private video" in error_msg:
                raise DownloadError("Это приватное видео")
            elif "Login required" in error_msg:
                raise DownloadError("Требуется авторизация")
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





