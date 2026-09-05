import csv
from datetime import datetime, timedelta
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot

@login_required
def reports_view(request):
    period = request.GET.get('period', '30d')
    report_type = request.GET.get('type', 'artists')
    artist_id = request.GET.get('artist', '')

    now = timezone.now()
    if period == '7d':
        start_date = now - timedelta(days=7)
    elif period == '90d':
        start_date = now - timedelta(days=90)
    elif period == 'all':
        start_date = now - timedelta(days=3650)
    else:  # '30d' default
        start_date = now - timedelta(days=30)

    artists = Artist.objects.filter(status=Artist.Status.ACTIVE).order_by('stage_name')

    rows = []
    if report_type == 'artists':
        query = artists
        if artist_id:
            query = query.filter(id=artist_id)

        for a in query:
            v_stats = Video.objects.filter(artist=a, is_active=True).aggregate(
                views=Sum('current_views'),
                likes=Sum('current_likes'),
                comments=Sum('current_comments'),
                count=Count('id')
            )
            gained = VideoStatisticSnapshot.objects.filter(
                video__artist=a,
                recorded_at__gte=start_date
            ).aggregate(g=Sum('views_change'))['g'] or 0

            subs = a.channel.subscriber_count if hasattr(a, 'channel') and a.channel else 0

            rows.append({
                'title': a.stage_name,
                'subtitle': a.genre,
                'subscribers': subs,
                'videos_count': v_stats['count'] or 0,
                'total_views': v_stats['views'] or 0,
                'views_gained': gained,
                'total_likes': v_stats['likes'] or 0,
                'total_comments': v_stats['comments'] or 0,
            })
    else:
        # Videos report
        query = Video.objects.filter(is_active=True).select_related('artist')
        if artist_id:
            query = query.filter(artist_id=artist_id)

        for v in query.order_by('-current_views')[:100]:
            gained = VideoStatisticSnapshot.objects.filter(
                video=v,
                recorded_at__gte=start_date
            ).aggregate(g=Sum('views_change'))['g'] or 0

            rows.append({
                'title': v.title,
                'subtitle': v.artist.stage_name,
                'subscribers': 0,
                'videos_count': 1,
                'total_views': v.current_views,
                'views_gained': gained,
                'total_likes': v.current_likes,
                'total_comments': v.current_comments,
                'like_rate': v.like_rate,
                'comment_rate': v.comment_rate,
            })

    return render(request, 'reports/index.html', {
        'artists': artists,
        'selected_artist': int(artist_id) if artist_id.isdigit() else '',
        'period': period,
        'report_type': report_type,
        'rows': rows,
        'start_date': start_date,
        'end_date': now,
    })

@login_required
def export_report_csv(request):
    period = request.GET.get('period', '30d')
    report_type = request.GET.get('type', 'artists')
    artist_id = request.GET.get('artist', '')

    now = timezone.now()
    if period == '7d':
        start_date = now - timedelta(days=7)
    elif period == '90d':
        start_date = now - timedelta(days=90)
    elif period == 'all':
        start_date = now - timedelta(days=3650)
    else:
        start_date = now - timedelta(days=30)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="youtube_analytics_report_{report_type}_{period}.csv"'

    writer = csv.writer(response)

    if report_type == 'artists':
        writer.writerow(['Artist Name', 'Genre', 'Subscribers', 'Total Videos', 'Total Views', f'Views Gained ({period})', 'Total Likes', 'Total Comments'])
        artists = Artist.objects.filter(status=Artist.Status.ACTIVE)
        if artist_id:
            artists = artists.filter(id=artist_id)

        for a in artists:
            v_stats = Video.objects.filter(artist=a, is_active=True).aggregate(
                views=Sum('current_views'), likes=Sum('current_likes'), comments=Sum('current_comments'), count=Count('id')
            )
            gained = VideoStatisticSnapshot.objects.filter(
                video__artist=a, recorded_at__gte=start_date
            ).aggregate(g=Sum('views_change'))['g'] or 0

            subs = a.channel.subscriber_count if hasattr(a, 'channel') and a.channel else 0
            writer.writerow([
                a.stage_name, a.genre, subs, v_stats['count'] or 0, v_stats['views'] or 0, gained, v_stats['likes'] or 0, v_stats['comments'] or 0
            ])
    else:
        writer.writerow(['Video Title', 'Artist', 'Release Date', 'Total Views', f'Views Gained ({period})', 'Likes', 'Comments', 'Like Rate (%)', 'Comment Rate (%)'])
        videos = Video.objects.filter(is_active=True).select_related('artist')
        if artist_id:
            videos = videos.filter(artist_id=artist_id)

        for v in videos.order_by('-current_views'):
            gained = VideoStatisticSnapshot.objects.filter(
                video=v, recorded_at__gte=start_date
            ).aggregate(g=Sum('views_change'))['g'] or 0

            writer.writerow([
                v.title, v.artist.stage_name, v.published_at.strftime('%Y-%m-%d'), v.current_views, gained, v.current_likes, v.current_comments, v.like_rate, v.comment_rate
            ])

    return response

@login_required
def printable_report_view(request):
    period = request.GET.get('period', '30d')
    report_type = request.GET.get('type', 'artists')
    artist_id = request.GET.get('artist', '')

    now = timezone.now()
    if period == '7d':
        start_date = now - timedelta(days=7)
    elif period == '90d':
        start_date = now - timedelta(days=90)
    else:
        start_date = now - timedelta(days=30)

    artists = Artist.objects.filter(status=Artist.Status.ACTIVE).order_by('stage_name')
    if artist_id:
        artists = artists.filter(id=artist_id)

    report_items = []
    for a in artists:
        v_stats = Video.objects.filter(artist=a, is_active=True).aggregate(
            views=Sum('current_views'),
            likes=Sum('current_likes'),
            comments=Sum('current_comments'),
            count=Count('id')
        )
        gained = VideoStatisticSnapshot.objects.filter(
            video__artist=a,
            recorded_at__gte=start_date
        ).aggregate(g=Sum('views_change'))['g'] or 0

        subs = a.channel.subscriber_count if hasattr(a, 'channel') and a.channel else 0
        top_songs = Video.objects.filter(artist=a, is_active=True).order_by('-current_views')[:5]

        report_items.append({
            'artist': a,
            'subscribers': subs,
            'total_videos': v_stats['count'] or 0,
            'total_views': v_stats['views'] or 0,
            'views_gained': gained,
            'total_likes': v_stats['likes'] or 0,
            'total_comments': v_stats['comments'] or 0,
            'top_songs': top_songs,
        })

    return render(request, 'reports/printable.html', {
        'report_items': report_items,
        'period': period,
        'start_date': start_date,
        'end_date': now,
    })
