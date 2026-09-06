import os
import re
import shutil
import tempfile
import logging
import urllib.request
from django.conf import settings
from django.core.files import File
from apps.studio.services.renderer import VideoStudioRenderer
from apps.studio.models import VideoProject

logger = logging.getLogger(__name__)


class AIDownloaderService:
    """
    Downloads audio streams from YouTube as lossless WAV or high-bitrate MP3,
    and bridges tracks directly to the 1-Hour Loop / Shorts Video Studio.
    """

    @classmethod
    def sanitize_filename(cls, name):
        """Sanitize filename to prevent file path and HTTP header issues"""
        clean = re.sub(r'[\\/*?:"<>|]', '', name)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean[:80] or "ai_track"

    @classmethod
    def download_audio_file(cls, video_url_or_id, audio_format='wav'):
        """
        Downloads the YouTube audio using yt-dlp and converts it to WAV or MP3.
        Returns the absolute filepath to the generated file, and the title.
        """
        import yt_dlp

        if not video_url_or_id.startswith('http'):
            youtube_url = f"https://www.youtube.com/watch?v={video_url_or_id}"
        else:
            youtube_url = video_url_or_id

        # Target temp directory
        download_dir = os.path.join(settings.MEDIA_ROOT, 'radar', 'downloads')
        os.makedirs(download_dir, exist_ok=True)

        ffmpeg_bin = VideoStudioRenderer.get_ffmpeg_binary()
        ffmpeg_dir = os.path.dirname(ffmpeg_bin) if ffmpeg_bin else None

        format_ext = 'wav' if audio_format.lower() == 'wav' else 'mp3'
        outtmpl = os.path.join(download_dir, f'%(title).60s_%(id)s.%(ext)s')

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': ffmpeg_dir or ffmpeg_bin,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': format_ext,
                'preferredquality': '0' if format_ext == 'wav' else '192',
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=True)
            title = info.get('title', 'AI Music Track')
            vid_id = info.get('id', 'video')

            # Find matching output file
            expected_filename = cls.sanitize_filename(title)
            final_path = None

            # Look in download_dir for the extracted file matching vid_id
            for f in os.listdir(download_dir):
                if vid_id in f and f.endswith(f'.{format_ext}'):
                    final_path = os.path.join(download_dir, f)
                    break

            if not final_path or not os.path.exists(final_path):
                # Fallback search
                for f in os.listdir(download_dir):
                    if f.endswith(f'.{format_ext}'):
                        final_path = os.path.join(download_dir, f)
                        break

            if not final_path or not os.path.exists(final_path):
                raise FileNotFoundError(f"Audio download completed but output {format_ext} file was not found.")

            return final_path, title

    @classmethod
    def import_track_to_studio(cls, video_id, title='AI Track', thumbnail_url='', video_format=VideoProject.VideoFormat.ONE_HOUR_LOOP):
        """
        Downloads audio + high-res cover art and creates a VideoProject in Video Studio.
        """
        # 1. Download audio in MP3 or WAV
        audio_path, extracted_title = cls.download_audio_file(video_id, audio_format='mp3')
        final_title = title if title and title != 'AI Track' else extracted_title

        # 2. Download thumbnail/artwork
        covers_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'covers')
        os.makedirs(covers_dir, exist_ok=True)
        cover_filename = f"radar_cover_{video_id}.jpg"
        cover_path = os.path.join(covers_dir, cover_filename)

        if not thumbnail_url:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

        try:
            req = urllib.request.Request(
                thumbnail_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response, open(cover_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
        except Exception:
            # Fallback to standard hqdefault
            try:
                fallback_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                req = urllib.request.Request(fallback_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as resp, open(cover_path, 'wb') as out_file:
                    shutil.copyfileobj(resp, out_file)
            except Exception as e:
                logger.warning(f"Could not download thumbnail: {e}")

        # 3. Create VideoProject record
        project = VideoProject(
            title=cls.sanitize_filename(final_title),
            video_format=video_format,
            render_status=VideoProject.Status.PENDING
        )

        with open(audio_path, 'rb') as af:
            project.audio_file.save(os.path.basename(audio_path), File(af), save=False)

        if os.path.exists(cover_path):
            with open(cover_path, 'rb') as cf:
                project.cover_image.save(cover_filename, File(cf), save=False)

        project.save()
        return project
