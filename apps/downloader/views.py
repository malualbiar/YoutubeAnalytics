import os
import re

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, FileResponse, Http404
from django.shortcuts import render, get_object_or_404, redirect
from django.views.decorators.http import require_POST, require_GET
from django.contrib import messages
from django.urls import reverse

from .models import DownloadJob
from . import services


# ── Title parsing helpers ─────────────────────────────────────────────────

# Common separators between artist and title in YouTube video names
_SEP_RE = re.compile(
    r'\s*(?:–|—|-|:|\|)\s*',
    re.UNICODE,
)

# Noise suffixes to strip from the clean title
_NOISE_SUFFIXES = re.compile(
    r'\s*[\(\[](official\s*(music\s*)?video|official\s*audio|lyrics?\s*video|'
    r'lyric\s*video|visualizer|hd|hq|4k|remastered|full\s*song|'
    r'classic\s*country\s*cover|cover|audio|official|live|'
    r'feat\.?.*?|ft\.?.*?)[\)\]]\s*$',
    re.IGNORECASE,
)


def _parse_yt_title(raw_title: str) -> tuple[str, str]:
    """
    Split a raw YouTube title into (clean_song_title, artist_name).
    Handles the common "Artist – Song Title (Official Video)" pattern.
    Returns ('', '') if the title is empty.
    """
    if not raw_title:
        return '', ''

    # Strip noise suffixes first
    cleaned = _NOISE_SUFFIXES.sub('', raw_title).strip()

    # Try to split on separator.
    # YouTube convention is almost always "Song Title - Artist Name",
    # so the FIRST part is the song title and the SECOND is the artist.
    parts = _SEP_RE.split(cleaned, maxsplit=1)
    if len(parts) == 2:
        title, artist = parts[0].strip(), parts[1].strip()
    else:
        title, artist = cleaned, ''

    # Final noise strip on both parts
    title  = _NOISE_SUFFIXES.sub('', title).strip()
    artist = _NOISE_SUFFIXES.sub('', artist).strip()
    return title, artist


def _cover_art_prompt(title: str, artist: str, uploader: str) -> str:
    """
    Build a ready-to-paste image generation prompt for a 1:1 cover art.
    """
    subject = f'"{title}"'
    if artist:
        subject += f' by {artist}'
    elif uploader:
        subject += f' by {uploader}'

    return (
        f"Square album cover art for the song {subject}. "
        "Photorealistic style, cinematic lighting, rich warm tones, "
        "elegant typography with the song title prominently placed, "
        "high detail, 1:1 aspect ratio, suitable for music streaming platforms. "
        "No text other than the song title."
    )


@login_required
def downloader_home_view(request):
    """Main YouTube Downloader page — shows form + download history."""
    jobs = DownloadJob.objects.filter(created_by=request.user).order_by('-created_at')[:50]
    # Mood labels for the server-rendered panel pills (mirrors PROMPT_TEMPLATES JS array)
    prompt_moods = [
        '🌅 Nostalgic', '🛣️ Freedom', '🎸 Intimate', '🌃 Mysterious', '🏔️ Hopeful',
        '🚚 Americana', '🌧️ Heartbreak', '🌸 Romantic', '🚗 Road Trip', '🪞 Reflective',
        '💃 Romance', '🌆 Energetic', '🏜️ Escape', '📷 Memory', '🌲 Solitude',
        '🌇 Reflection', '🎙️ Authentic', '🌙 Longing', '🎉 Carefree', '💔 Loss',
        '👤 My Photo',
    ]
    return render(request, 'downloader/index.html', {
        'jobs': jobs,
        'format_choices': DownloadJob.Format.choices,
        'prompt_moods': prompt_moods,
    })


@login_required
@require_GET
def downloader_fetch_info_api(request):
    """AJAX: fetch video metadata (title, thumbnail, duration) for a URL."""
    url = request.GET.get('url', '').strip()
    if not url:
        return JsonResponse({'error': 'No URL provided.'}, status=400)

    try:
        info = services.fetch_video_info(url)
        return JsonResponse({'success': True, 'info': info})
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=400)


@login_required
@require_POST
def downloader_start_view(request):
    """AJAX / form POST: create a DownloadJob and start the background download."""
    url = request.POST.get('url', '').strip()
    fmt = request.POST.get('format', DownloadJob.Format.MP3_320)
    prefill_title = request.POST.get('title', '').strip()

    if not url:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'error': 'No URL provided.'}, status=400)
        messages.error(request, 'Please enter a YouTube URL.')
        return redirect('downloader_home')

    if fmt not in dict(DownloadJob.Format.choices):
        fmt = DownloadJob.Format.MP3_320

    # Fetch metadata so we have a title and thumbnail before download completes
    title = prefill_title
    thumbnail = ''
    duration = 0
    uploader = ''
    try:
        info = services.fetch_video_info(url)
        title = title or info.get('title', '')
        thumbnail = info.get('thumbnail', '')
        duration = info.get('duration_seconds', 0)
        uploader = info.get('uploader', '')
    except Exception:
        pass

    job = DownloadJob.objects.create(
        url=url,
        title=title,
        uploader=uploader,
        thumbnail_url=thumbnail,
        duration_seconds=duration,
        format=fmt,
        status=DownloadJob.Status.DOWNLOADING,
        progress=0,
        progress_text='Starting download…',
        created_by=request.user,
    )

    def _on_progress(pct, text):
        DownloadJob.objects.filter(pk=job.pk).update(progress=pct, progress_text=text)

    def _on_done(abs_path, file_size):
        from django.conf import settings as _s
        rel = os.path.relpath(abs_path, str(_s.MEDIA_ROOT))
        DownloadJob.objects.filter(pk=job.pk).update(
            status=DownloadJob.Status.COMPLETED,
            output_file=rel,
            file_size_bytes=file_size,
            progress=100,
            progress_text='Download complete!',
        )

    def _on_error(msg):
        DownloadJob.objects.filter(pk=job.pk).update(
            status=DownloadJob.Status.FAILED,
            error_message=msg,
            progress_text=f'Failed: {msg}',
        )

    services.download_video(
        job_id=job.pk,
        url=url,
        fmt=fmt,
        title=title,
        on_progress=_on_progress,
        on_done=_on_done,
        on_error=_on_error,
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'job_id': job.pk,
            'title': job.title,
            'thumbnail': job.thumbnail_url,
            'format': job.get_format_display(),
        })

    messages.success(request, f"Download started for \"{job.title or url}\".")
    return redirect('downloader_home')


@login_required
@require_GET
def downloader_progress_api(request, pk):
    """AJAX: poll download progress for a job."""
    job = get_object_or_404(DownloadJob, pk=pk, created_by=request.user)
    return JsonResponse({
        'status': job.status,
        'progress': job.progress,
        'text': job.progress_text,
        'title': job.title,
        'file_size': job.file_size_formatted,
        'error': job.error_message,
    })


@login_required
@require_POST
def downloader_delete_view(request, pk):
    """Delete a download job and its file."""
    job = get_object_or_404(DownloadJob, pk=pk, created_by=request.user)
    if job.output_file:
        try:
            job.output_file.delete(save=False)
        except Exception:
            pass
    job.delete()
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True})
    messages.info(request, 'Download removed.')
    return redirect('downloader_home')


@login_required
def downloader_file_view(request, pk):
    """Serve the completed file as a direct download."""
    job = get_object_or_404(DownloadJob, pk=pk, created_by=request.user)
    if job.status != DownloadJob.Status.COMPLETED or not job.output_file:
        raise Http404("File not available.")

    abs_path = job.output_file.path
    if not os.path.exists(abs_path):
        raise Http404("File not found on disk.")

    filename = os.path.basename(abs_path)
    response = FileResponse(open(abs_path, 'rb'), as_attachment=True, filename=filename)
    return response


@login_required
@require_GET
def prepare_lyrics_api(request, pk):
    """
    AJAX: return parsed title, artist, cover-art prompt, and the audio URL
    for a completed download so the downloader page can show an inline panel.
    """
    job = get_object_or_404(DownloadJob, pk=pk, created_by=request.user)

    if job.status != DownloadJob.Status.COMPLETED or not job.output_file:
        return JsonResponse({'error': 'Download not ready.'}, status=400)

    clean_title, artist = _parse_yt_title(job.title)
    if not clean_title:
        clean_title = job.title

    prompt = _cover_art_prompt(clean_title, artist, job.uploader)

    from urllib.parse import urlencode
    lyrics_url = reverse('lyrics_maker') + '?' + urlencode({
        'prefill_title': clean_title,
        'prefill_artist': artist,
        'prefill_prompt': prompt,
        'from_job': pk,
    })

    return JsonResponse({
        'title': clean_title,
        'artist': artist,
        'prompt': prompt,
        'audio_url': job.output_file.url,
        'lyrics_url': lyrics_url,
    })
