from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video
from .services import AnalyticsService

@login_required
def dashboard_view(request):
    AnalyticsService.update_video_growth_metrics()
    summary = AnalyticsService.get_dashboard_summary()
    
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
