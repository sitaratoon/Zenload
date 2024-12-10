import logging
import asyncio
from pathlib import Path
from typing import Optional, Tuple, List, Dict
import yt_dlp
from .base import BaseDownloader, DownloadError

logger = logging.getLogger(__name__)

class PinterestDownloader(BaseDownloader):
    def __init__(self):
        super().__init__()
        # Set default yt-dlp options for Pinterest
        self.ydl_opts.update({
            'format': 'best',
            'nooverwrites': True,
            'no_color': True,
            'no_warnings': True,
            'quiet': False,
        })

    def platform_id(self) -> str:
        """Return platform identifier"""
        return 'pinterest'

    def can_handle(self, url: str) -> bool:
        """Check if URL is from Pinterest"""
        return any(x in url.lower() for x in ['pinterest.com', 'pin.it'])

    async def get_formats(self, url: str) -> List[Dict]:
        """Get available formats for URL"""
        try:
            self.update_progress('status_getting_info', 0)
            logger.info(f"[Pinterest] Getting formats for: {url}")

            # Create download directory if not exists
            download_dir = Path(__file__).parent.parent.parent / "downloads"
            download_dir.mkdir(exist_ok=True)
            
            # Extract info using yt-dlp
            ydl_opts = self.ydl_opts.copy()
            ydl_opts.update({
                'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
            })

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.update_progress('status_getting_info', 30)
                info = await asyncio.to_thread(
                    ydl.extract_info, url, download=False
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
                                'ext': f.get('ext', 'mp4')
                            })
                            seen.add(quality)
                    
                    if formats:
                        logger.info("[Pinterest] Successfully extracted formats")
                        return sorted(formats, key=lambda x: int(x['quality'][:-1]), reverse=True)

            raise DownloadError("Не удалось получить информацию о медиафайле")

        except Exception as e:
            logger.error(f"[Pinterest] Format extraction failed: {e}")
            raise DownloadError(f"Ошибка при получении форматов: {str(e)}")

    async def download(self, url: str, format_id: Optional[str] = None) -> Tuple[str, Path]:
        """Download video from URL"""
        try:
            self.update_progress('status_downloading', 0)
            logger.info(f"[Pinterest] Downloading from: {url}")

            # Create download directory if not exists
            download_dir = Path(__file__).parent.parent.parent / "downloads"
            download_dir.mkdir(exist_ok=True)
            download_dir = download_dir.resolve()  # Get absolute path
            
            # Set up yt-dlp options
            ydl_opts = self.ydl_opts.copy()
            if format_id:
                ydl_opts['format'] = format_id
            ydl_opts.update({
                'outtmpl': str(download_dir / '%(id)s.%(ext)s'),
            })

            # Download using yt-dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.update_progress('status_downloading', 20)
                info = await asyncio.to_thread(
                    ydl.extract_info, url, download=True
                )
                
                if info:
                    # Get downloaded file path and verify it exists
                    filename = ydl.prepare_filename(info)
                    file_path = Path(filename).resolve()
                    if file_path.exists():
                        logger.info("[Pinterest] Successfully downloaded content")
                        return self._prepare_metadata(info), file_path

            raise DownloadError("Не удалось загрузить медиафайл")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Pinterest] Download failed: {error_msg}")
            raise DownloadError(f"Ошибка загрузки: {error_msg}")

    def _prepare_metadata(self, info: Dict) -> str:
        """Prepare metadata string from info"""
        def format_number(num):
            if not num:
                return "0"
            if num >= 1000000:
                return f"{num/1000000:.1f}M"
            if num >= 1000:
                return f"{num/1000:.1f}K"
            return str(num)

        title = info.get('title', '')
        uploader = info.get('uploader', '')
        view_count = format_number(info.get('view_count', 0))

        metadata_parts = ["Pinterest"]
        if view_count != "0":
            metadata_parts.append(f"{view_count} views")
        if uploader:
            metadata_parts.append(f"by {uploader}")
        if title:
            metadata_parts.append(f"\n{title}")

        return " | ".join(metadata_parts)
