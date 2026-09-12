"""
YouTube Downloader service using yt-dlp + FFmpeg.

Handles:
  - Video metadata fetching (title, thumbnail, duration, formats)
  - Async downloading with live progress callbacks
  - MP4 (best video+audio merged via FFmpeg) at 1080p / 720p / 480p
  - MP3 extraction at 320 / 192 / 128 kbps via FFmpeg post-processor
"""

import glob
import os
import re
import sys
import shutil
import threading

import yt_dlp

from django.conf import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _downloads_dir() -> str:
    path = os.path.join(settings.MEDIA_ROOT, 'downloads')
    os.makedirs(path, exist_ok=True)
    return path


def _get_ffmpeg_binary() -> str:
    """
    Locate the FFmpeg executable using the same resolution order as the rest
    of the project (renderer.py), so yt-dlp always finds the bundled binary.
    """
    # 1. Bundled project binary
    local_bin = os.path.join(settings.BASE_DIR, 'bin', 'ffmpeg.exe')
    if os.path.exists(local_bin):
        return local_bin

    # 2. imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except Exception:
        pass

    # 3. System PATH
    system = shutil.which('ffmpeg')
    if system:
        return system

    # 4. site-packages scan
    for p in sys.path:
        for match in glob.glob(os.path.join(p, 'imageio_ffmpeg', 'binaries', 'ffmpeg*')):
            if os.path.exists(match) and match.endswith('.exe'):
                return match

    raise FileNotFoundError(
        "FFmpeg executable not found. Install FFmpeg or ensure bin/ffmpeg.exe exists."
    )


# All formats pull the best available audio stream
_AUDIO_FORMAT_SELECTOR = 'bestaudio/best'

# Format → FFmpeg postprocessor config
# codec: None means copy-to-wav via pcm_s16le; yt-dlp handles WAV natively.
_POSTPROCESSORS = {
    'mp3_320': {'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'},
    'wav':     {'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav', 'preferredquality': '0'},
}

_FORMAT_EXTENSIONS = {
    'mp3_320': 'mp3',
    'wav':     'wav',
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_video_info(url: str) -> dict:
    """
    Return basic metadata for *url* without downloading anything.
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = []
    for f in info.get('formats', []):
        formats.append({
            'format_id': f.get('format_id', ''),
            'ext': f.get('ext', ''),
            'height': f.get('height'),
            'abr': f.get('abr'),
            'filesize_approx': f.get('filesize_approx') or f.get('filesize') or 0,
        })

    return {
        'title': info.get('title', ''),
        'uploader': info.get('uploader', '') or info.get('channel', ''),
        'thumbnail': info.get('thumbnail', ''),
        'duration_seconds': int(info.get('duration') or 0),
        'webpage_url': info.get('webpage_url', url),
        'formats': formats,
    }


def download_video(job_id: int, url: str, fmt: str, title: str,
                   on_progress=None, on_done=None, on_error=None):
    """
    Download *url* in a background daemon thread.

    :param job_id:      DownloadJob.pk (used as a filename prefix)
    :param url:         YouTube (or any yt-dlp-supported) URL
    :param fmt:         One of DownloadJob.Format choices
    :param title:       Video title (used for the filename)
    :param on_progress: callable(percent: int, text: str)
    :param on_done:     callable(abs_path: str, file_size: int)
    :param on_error:    callable(error_msg: str)
    """
    def _run():
        output_dir = _downloads_dir()
        final_ext = _FORMAT_EXTENSIONS.get(fmt, 'mp3')

        # Use job_id as a stable prefix so we can locate the file afterwards.
        # %(ext)s is required by yt-dlp; the real extension may differ before
        # post-processing, so we scan by prefix once the download finishes.
        out_tmpl = os.path.join(output_dir, f"{job_id}_%(title).100B.%(ext)s")

        def _progress_hook(d):
            if d['status'] == 'downloading':
                downloaded = d.get('downloaded_bytes') or 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                if total > 0:
                    pct = min(99, int(downloaded / total * 100))
                else:
                    pct = 0
                speed = d.get('_speed_str', '').strip()
                eta = d.get('_eta_str', '').strip()
                text = f"Downloading… {pct}%"
                if speed and speed != 'Unknown B/s':
                    text += f"  ·  {speed}"
                if eta and eta != 'Unknown':
                    text += f"  ·  ETA {eta}"
                if on_progress:
                    on_progress(pct, text)
            elif d['status'] == 'finished':
                if on_progress:
                    on_progress(99, 'Processing with FFmpeg…')

        try:
            ffmpeg_bin = _get_ffmpeg_binary()
        except FileNotFoundError as exc:
            if on_error:
                on_error(str(exc))
            return

        postprocessor = _POSTPROCESSORS.get(fmt, _POSTPROCESSORS['mp3_320'])

        ydl_opts = {
            'format': _AUDIO_FORMAT_SELECTOR,
            'outtmpl': out_tmpl,
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'progress_hooks': [_progress_hook],
            'ffmpeg_location': os.path.dirname(ffmpeg_bin),
            'postprocessors': [postprocessor],
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            # Locate the output file: scan for any file starting with job_id
            # and ending with the expected extension (yt-dlp may sanitise the
            # title differently than we would).
            candidates = sorted([
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.startswith(f"{job_id}_") and f.endswith(f'.{final_ext}')
            ], key=os.path.getmtime, reverse=True)

            if not candidates:
                # Fallback: pick the most-recently modified file with this prefix
                candidates = sorted([
                    os.path.join(output_dir, f)
                    for f in os.listdir(output_dir)
                    if f.startswith(f"{job_id}_")
                ], key=os.path.getmtime, reverse=True)

            if not candidates:
                raise FileNotFoundError(
                    f"Download completed but output file not found in {output_dir}"
                )

            out_path = candidates[0]
            file_size = os.path.getsize(out_path)
            if on_done:
                on_done(out_path, file_size)

        except Exception as exc:
            if on_error:
                on_error(str(exc))

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
