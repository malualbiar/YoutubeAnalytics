from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Video, VideoStatisticSnapshot
from apps.artists.models import Artist
from apps.analytics.services import AnalyticsService

@login_required
def video_list_view(request):
    AnalyticsService.update_video_growth_metrics()
    search_query = request.GET.get('q', '').strip()
    artist_id = request.GET.get('artist', '').strip()
    sort_by = request.GET.get('sort', 'total_views')

    videos_query = Video.objects.filter(is_active=True).select_related('artist', 'channel')

    if search_query:
        videos_query = videos_query.filter(
            Q(title__icontains=search_query) |
            Q(artist__stage_name__icontains=search_query) |
            Q(channel__channel_name__icontains=search_query)
        )

    if artist_id:
        videos_query = videos_query.filter(artist_id=artist_id)

    # Sorting
    if sort_by == 'views_today':
        videos_query = videos_query.order_by('-views_today', '-current_views')
    elif sort_by == 'views_this_week':
        videos_query = videos_query.order_by('-views_this_week', '-current_views')
    elif sort_by == 'views_this_month':
        videos_query = videos_query.order_by('-views_this_month', '-current_views')
    elif sort_by == 'likes':
        videos_query = videos_query.order_by('-current_likes')
    elif sort_by == 'comments':
        videos_query = videos_query.order_by('-current_comments')
    elif sort_by == 'recent':
        videos_query = videos_query.order_by('-published_at')
    else:  # 'total_views' default
        videos_query = videos_query.order_by('-current_views')

    paginator = Paginator(videos_query, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    artists = Artist.objects.all().order_by('stage_name')

    return render(request, 'videos/list.html', {
        'page_obj': page_obj,
        'artists': artists,
        'search_query': search_query,
        'selected_artist': int(artist_id) if artist_id.isdigit() else '',
        'sort_by': sort_by,
        'total_count': paginator.count,
    })

@login_required
def video_detail_view(request, pk):
    AnalyticsService.update_video_growth_metrics(video_ids=[pk])
    video = get_object_or_404(Video.objects.select_related('artist', 'channel'), pk=pk)
    
    range_days_param = request.GET.get('days', '30')
    if range_days_param == 'all':
        range_days = 'all'
    else:
        try:
            range_days = int(range_days_param)
        except (ValueError, TypeError):
            range_days = 30

    chart_data = AnalyticsService.get_views_growth_chart_data(days=range_days, video_id=video.id)

    snapshots = video.snapshots.all().order_by('-recorded_at')[:30]
    milestones = video.milestones.all().order_by('-reached_at')

    # Calculate total views gained in this range
    total_gained_in_period = sum(chart_data['views_gained'])

    return render(request, 'videos/detail.html', {
        'video': video,
        'chart_data': chart_data,
        'range_days': range_days,
        'snapshots': snapshots,
        'milestones': milestones,
        'total_gained_in_period': total_gained_in_period,
    })
