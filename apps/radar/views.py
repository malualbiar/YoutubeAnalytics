import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, Http404, JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from apps.radar.services.ai_radar_service import AIRadarService
from apps.radar.services.downloader_service import AIDownloaderService
from apps.studio.models import VideoProject


@login_required
def radar_feed_view(request):
    """
    AI Music Discovery Radar dashboard with granular time, duration,
    and channel popularity filters.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    query = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', 'all')
    time_window = request.GET.get('time', '48h')
    duration = request.GET.get('duration', 'all')
    popularity = request.GET.get('popularity', 'all')
    sort_by = request.GET.get('sort', 'velocity')
    detection_mode = request.GET.get('mode', 'all')
    force_refresh = bool(request.GET.get('refresh'))
    show_sections = request.GET.get('view', 'grid') == 'sections'

    tracks = AIRadarService.get_recent_ai_music(
        query=query,
        genre=genre,
        time_window=time_window,
        duration=duration,
        popularity=popularity,
        sort_by=sort_by,
        detection_mode=detection_mode,
        max_results=36,
        force_refresh=force_refresh
    )

    # Genre-sectioned top tracks panel (lazy — only fetched when sections view active
    # OR when on the default landing with no active filters)
    genre_sections = []
    if show_sections or (not query and genre == 'all' and detection_mode == 'all'):
        genre_sections = AIRadarService.get_genre_top_tracks(
            time_window=time_window,
            top_n=5,
            force_refresh=force_refresh,
        )

    genres = [
        {'id': 'all',          'label': 'All AI Music'},
        {'id': 'most_searched','label': '🔥 Most Searched'},
        {'id': 'trending',     'label': '📈 Trending Now'},
        {'id': 'ai_unlabeled', 'label': '🕵️ AI Untagged'},
        {'id': 'suno',         'label': 'Suno AI'},
        {'id': 'udio',         'label': 'Udio AI'},
        {'id': 'pop',          'label': 'Pop & EDM'},
        {'id': 'rap',          'label': 'Phonk & Hip-Hop'},
        {'id': 'rnb',          'label': 'R&B & Soul'},
        {'id': 'rock',         'label': 'Rock & Metal'},
        {'id': 'country',      'label': 'Country'},
        {'id': 'gospel',       'label': 'Gospel'},
        {'id': 'reggae',       'label': 'Reggae'},
        {'id': 'lofi',         'label': 'Lofi & Chill'},
        {'id': 'synthwave',    'label': 'Synthwave'},
    ]

    detection_modes = [
        {'id': 'all',         'label': 'All AI Music'},
        {'id': 'yt_flagged',  'label': '🛡️ YT-Flagged AI'},
        {'id': 'ai_unlabeled','label': '🕵️ AI Untagged'},
    ]

    time_windows = [
        {'id': '30m', 'label': 'Past 30 mins'},
        {'id': '1h', 'label': 'Past 1 hour'},
        {'id': '6h', 'label': 'Past 6 hours'},
        {'id': '12h', 'label': 'Past 12 hours'},
        {'id': '24h', 'label': 'Past 24 hours'},
        {'id': '48h', 'label': 'Past 48 hours'},
        {'id': '7d', 'label': 'Past 7 days'},
        {'id': '30d', 'label': 'Past 30 days'},
    ]

    duration_options = [
        {'id': 'all', 'label': 'Any Length'},
        {'id': 'under_3', 'label': '< 3 mins'},
        {'id': '3_to_6', 'label': '3 – 6 mins'},
        {'id': '6_to_10', 'label': '6 – 10 mins'},
        {'id': 'over_10', 'label': '> 10 mins (Extended)'},
    ]

    popularity_options = [
        {'id': 'all', 'label': 'All Channels'},
        {'id': 'popular', 'label': 'Popular Channels (>10k views)'},
        {'id': 'rising', 'label': 'Rising / Underdog (<10k views)'},
    ]

    sort_options = [
        {'id': 'velocity', 'label': 'Highest Velocity (Views/Hr)'},
        {'id': 'date', 'label': 'Most Recent'},
        {'id': 'views', 'label': 'Most Views'},
        {'id': 'likes', 'label': 'Most Likes'},
    ]

    context = {
        'tracks': tracks,
        'total_tracks': len(tracks),
        'query': query,
        'current_genre': genre,
        'current_time': time_window,
        'current_duration': duration,
        'current_popularity': popularity,
        'current_sort': sort_by,
        'current_mode': detection_mode,
        'show_sections': show_sections,
        'genre_sections': genre_sections,
        'genres': genres,
        'detection_modes': detection_modes,
        'time_windows': time_windows,
        'duration_options': duration_options,
        'popularity_options': popularity_options,
        'sort_options': sort_options,
        'format_choices': VideoProject.VideoFormat.choices,
    }

    return render(request, 'radar/index.html', context)


@login_required
def download_audio_view(request):
    """
    Directly downloads audio from YouTube as uncompressed lossless WAV or MP3.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    video_id = request.GET.get('video_id') or request.POST.get('video_id')
    audio_format = (request.GET.get('format') or request.POST.get('format') or 'wav').lower()
    custom_title = request.GET.get('title') or request.POST.get('title') or 'AI Track'

    if not video_id:
        messages.error(request, "Video ID or URL is required for download.")
        return redirect('radar_feed')

    try:
        file_path, extracted_title = AIDownloaderService.download_audio_file(
            video_url_or_id=video_id,
            audio_format=audio_format
        )

        final_title = custom_title if custom_title and custom_title != 'AI Track' else extracted_title
        clean_filename = AIDownloaderService.sanitize_filename(final_title)
        extension = 'wav' if audio_format == 'wav' else 'mp3'
        download_name = f"{clean_filename}.{extension}"

        content_type = 'audio/wav' if audio_format == 'wav' else 'audio/mpeg'

        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="{download_name}"'
        return response

    except Exception as e:
        messages.error(request, f"Audio download error: {str(e)}")
        return redirect('radar_feed')


@login_required
@require_POST
def import_to_studio_view(request):
    """
    One-click bridge to download track & cover, creating a VideoProject in Video Studio.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    video_id = request.POST.get('video_id')
    title = request.POST.get('title', 'AI Track')
    thumbnail_url = request.POST.get('thumbnail_url', '')
    video_format = request.POST.get('video_format', VideoProject.VideoFormat.ONE_HOUR_LOOP)

    if not video_id:
        messages.error(request, "Video ID is required to import to Video Studio.")
        return redirect('radar_feed')

    try:
        project = AIDownloaderService.import_track_to_studio(
            video_id=video_id,
            title=title,
            thumbnail_url=thumbnail_url,
            video_format=video_format
        )
        messages.success(
            request,
            f"Successfully imported '{project.title}' into Video Studio! Ready to render."
        )
        return redirect('studio_home')

    except Exception as e:
        messages.error(request, f"Failed to import track to Video Studio: {str(e)}")
        return redirect('radar_feed')
