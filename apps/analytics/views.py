from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import JsonResponse
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video
from .services import AnalyticsService

@login_required
def dashboard_view(request):
    AnalyticsService.update_video_growth_metrics()
    summary = AnalyticsService.get_dashboard_summary()
    daily_posting = AnalyticsService.get_daily_posting_status()
    active_artists = Artist.objects.filter(status=Artist.Status.ACTIVE).order_by('stage_name')
    
    range_days_param = request.GET.get('days', '30')
    if range_days_param == 'all':
        range_days = 'all'
    else:
        try:
            range_days = int(range_days_param)
        except (ValueError, TypeError):
            range_days = 30

    chart_data = AnalyticsService.get_views_growth_chart_data(days=range_days)
    
    top_sort = request.GET.get('top_sort', 'total_views')
    top_videos = AnalyticsService.get_top_videos(sort_by=top_sort, limit=6)
    fastest_growing = AnalyticsService.get_fastest_growing_videos(limit=5)

    return render(request, 'dashboard/index.html', {
        'summary': summary,
        'daily_posting': daily_posting,
        'active_artists': active_artists,
        'chart_data': chart_data,
        'range_days': range_days,
        'top_videos': top_videos,
        'fastest_growing': fastest_growing,
        'top_sort': top_sort,
    })

@login_required
def artist_comparison_view(request):
    all_artists = Artist.objects.filter(status=Artist.Status.ACTIVE).order_by('stage_name')
    
    selected_ids = request.GET.getlist('artists')
    if not selected_ids:
        # Default to first 2-3 artists if available
        first_artists = all_artists[:3]
        selected_ids = [str(a.id) for a in first_artists]

    int_ids = [int(i) for i in selected_ids if i.isdigit()]
    comparison_data = AnalyticsService.get_artist_comparison(int_ids)

    return render(request, 'comparisons/artists.html', {
        'all_artists': all_artists,
        'selected_ids': int_ids,
        'comparison_matrix': comparison_data['comparison_matrix'],
        'chart_labels': comparison_data['chart_labels'],
        'chart_datasets': comparison_data['chart_datasets'],
    })

@login_required
def video_comparison_view(request):
    all_videos = Video.objects.filter(is_active=True).select_related('artist').order_by('-current_views')[:50]
    
    selected_ids = request.GET.getlist('videos')
    if not selected_ids:
        first_videos = all_videos[:3]
        selected_ids = [str(v.id) for v in first_videos]

    int_ids = [int(i) for i in selected_ids if i.isdigit()]
    comparison_data = AnalyticsService.get_video_comparison(int_ids)

    return render(request, 'comparisons/videos.html', {
        'all_videos': all_videos,
        'selected_ids': int_ids,
        'comparison_matrix': comparison_data['comparison_matrix'],
        'chart_labels': comparison_data['chart_labels'],
        'chart_datasets': comparison_data['chart_datasets'],
    })

@login_required
def global_search_view(request):
    """API endpoint for live search in global search modal"""
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 2:
        return JsonResponse({'artists': [], 'videos': [], 'channels': []})

    artists = Artist.objects.filter(stage_name__icontains=q)[:5]
    channels = YouTubeChannel.objects.filter(channel_name__icontains=q)[:5]
    videos = Video.objects.filter(title__icontains=q).select_related('artist')[:8]

    artists_data = [{
        'id': a.id,
        'name': a.stage_name,
        'url': f'/artists/{a.id}/',
        'image': a.profile_image or '',
        'genre': a.genre
    } for a in artists]

    channels_data = [{
        'id': c.id,
        'name': c.channel_name,
        'url': f'/artists/{c.artist.id}/',
        'thumbnail': c.thumbnail_url or '',
        'subscribers': c.subscriber_count
    } for c in channels]

    videos_data = [{
        'id': v.id,
        'title': v.title,
        'artist': v.artist.stage_name,
        'url': f'/videos/{v.id}/',
        'thumbnail': v.thumbnail_url or '',
        'views': v.current_views
    } for v in videos]

    return JsonResponse({
        'artists': artists_data,
        'channels': channels_data,
        'videos': videos_data
    })

@login_required
def daily_posting_status_api(request):
    """API endpoint for fetching live daily posting status and reminder configuration"""
    status = AnalyticsService.get_daily_posting_status()
    uploads_serialized = []
    for u in status['today_uploads']:
        uploads_serialized.append({
            'id': u['id'],
            'raw_id': u['raw_id'],
            'is_manual': u['is_manual'],
            'title': u['title'],
            'platform': u['platform'],
            'platform_display': u['platform_display'],
            'artist_name': u['artist_name'],
            'artist_image': u['artist_image'],
            'url': u['url'],
            'posted_at': u['posted_at'].strftime('%H:%M') if hasattr(u['posted_at'], 'strftime') else str(u['posted_at']),
            'notes': u['notes'],
            'thumbnail': u['thumbnail'],
        })

    return JsonResponse({
        'target': status['target'],
        'today_count': status['today_count'],
        'remaining': status['remaining'],
        'progress_pct': status['progress_pct'],
        'is_goal_met': status['is_goal_met'],
        'current_streak': status['current_streak'],
        'best_streak': status['best_streak'],
        'reminders_enabled': status['reminders_enabled'],
        'reminder_frequency_hours': status['reminder_frequency_hours'],
        'reminder_start_hour': status['reminder_start_hour'],
        'reminder_end_hour': status['reminder_end_hour'],
        'history_30d': status['history_30d'],
        'today_uploads': uploads_serialized,
    })

@login_required
@require_POST
def log_content_upload_view(request):
    """Form handler to log a manual content upload (Shorts, TikTok, Reels, etc.)"""
    title = request.POST.get('title', '').strip()
    platform = request.POST.get('platform', 'youtube_short')
    artist_id = request.POST.get('artist_id')
    url = request.POST.get('url', '').strip()
    notes = request.POST.get('notes', '').strip()

    if not title:
        messages.error(request, "Content title is required.")
        return redirect('dashboard')

    AnalyticsService.log_content_upload(
        title=title,
        platform=platform,
        artist_id=artist_id if (artist_id and artist_id.isdigit()) else None,
        url=url,
        notes=notes
    )
    messages.success(request, f"Logged upload: '{title}' (+1 towards today's goal!)")
    return redirect('dashboard')

@login_required
@require_POST
def delete_content_upload_view(request, pk):
    """Remove a manual content upload log"""
    AnalyticsService.delete_content_upload(pk)
    messages.info(request, "Content upload record removed.")
    return redirect('dashboard')

