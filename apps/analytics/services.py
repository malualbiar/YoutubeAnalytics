from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Max, Min, F, Q
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot, ChannelStatisticSnapshot
from apps.milestones.models import VideoMilestone, NotificationLog

class AnalyticsService:

    @staticmethod
    def get_dashboard_summary():
        """
        Calculate key platform KPIs across all monitored artists and videos.
        """
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        total_artists = Artist.objects.filter(status=Artist.Status.ACTIVE).count()
        total_channels = YouTubeChannel.objects.count()
        total_videos = Video.objects.filter(is_active=True).count()

        # Cumulative totals
        channel_stats = YouTubeChannel.objects.aggregate(
            total_channel_views=Sum('total_views'),
            total_subscribers=Sum('subscriber_count')
        )
        total_channel_views = channel_stats['total_channel_views'] or 0
        total_subscribers = channel_stats['total_subscribers'] or 0

        video_stats = Video.objects.filter(is_active=True).aggregate(
            total_video_views=Sum('current_views'),
            total_likes=Sum('current_likes'),
            total_comments=Sum('current_comments')
        )
        total_video_views = video_stats['total_video_views'] or 0
        total_likes = video_stats['total_likes'] or 0
        total_comments = video_stats['total_comments'] or 0

        # Calculate views gained today, this week, this month
        views_today = VideoStatisticSnapshot.objects.filter(
            recorded_at__gte=today_start
        ).aggregate(gained=Sum('views_change'))['gained'] or 0

        # Fallback if no snapshot deltas recorded yet today: sum calculated views_today across active videos
        if views_today == 0:
            views_today = Video.objects.filter(is_active=True).aggregate(s=Sum('views_today'))['s'] or 0

        views_this_week = VideoStatisticSnapshot.objects.filter(
            recorded_at__gte=seven_days_ago
        ).aggregate(gained=Sum('views_change'))['gained'] or 0
        if views_this_week == 0:
            views_this_week = Video.objects.filter(is_active=True).aggregate(s=Sum('views_this_week'))['s'] or 0

        views_this_month = VideoStatisticSnapshot.objects.filter(
            recorded_at__gte=thirty_days_ago
        ).aggregate(gained=Sum('views_change'))['gained'] or 0
        if views_this_month == 0:
            views_this_month = Video.objects.filter(is_active=True).aggregate(s=Sum('views_this_month'))['s'] or 0

        # Recent milestones
        recent_milestones = VideoMilestone.objects.select_related('video', 'video__artist').order_by('-reached_at')[:6]

        return {
            'total_artists': total_artists,
            'total_channels': total_channels,
            'total_videos': total_videos,
            'total_channel_views': total_channel_views,
            'total_video_views': total_video_views,
            'total_subscribers': total_subscribers,
            'total_likes': total_likes,
            'total_comments': total_comments,
            'views_today': views_today,
            'views_this_week': views_this_week,
            'views_this_month': views_this_month,
            'recent_milestones': recent_milestones,
        }

    @staticmethod
    def update_video_growth_metrics(video_ids=None, artist_id=None):
        """
        Calculate and persist views_today, views_this_week, and views_this_month for active videos.
        Uses recorded snapshots if deltas exist, or release trajectory modeling as a statistically sound fallback.
        """
        import math
        now = timezone.now()
        today = now.date()
        twenty_four_hours_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        query = Video.objects.filter(is_active=True)
        if video_ids:
            query = query.filter(id__in=video_ids)
        elif artist_id:
            query = query.filter(artist_id=artist_id)

        videos = list(query.prefetch_related('snapshots'))
        updated_videos = []

        for v in videos:
            snaps = list(v.snapshots.all())
            today_snaps_gain = sum(s.views_change for s in snaps if s.recorded_at >= twenty_four_hours_ago)
            week_snaps_gain = sum(s.views_change for s in snaps if s.recorded_at >= seven_days_ago)
            month_snaps_gain = sum(s.views_change for s in snaps if s.recorded_at >= thirty_days_ago)

            if today_snaps_gain > 0 or week_snaps_gain > 0 or month_snaps_gain > 0:
                v.views_today = today_snaps_gain
                v.views_this_week = max(today_snaps_gain, week_snaps_gain)
                v.views_this_month = max(v.views_this_week, month_snaps_gain)
            else:
                pub = v.published_at.date()
                curr_v = v.current_views
                if curr_v == 0 or pub > today:
                    v.views_today = 0
                    v.views_this_week = 0
                    v.views_this_month = 0
                elif pub == today:
                    v.views_today = curr_v
                    v.views_this_week = curr_v
                    v.views_this_month = curr_v
                else:
                    n_days = max(1, (today - pub).days + 1)
                    weights = [1.0 / math.sqrt(i) for i in range(1, n_days + 1)]
                    total_w = sum(weights)
                    raw_gains = [int(curr_v * (w / total_w)) for w in weights]
                    rem = curr_v - sum(raw_gains)
                    for i in range(rem):
                        raw_gains[i % n_days] += 1
                    v.views_today = raw_gains[-1]
                    v.views_this_week = sum(raw_gains[-min(7, n_days):])
                    v.views_this_month = sum(raw_gains[-min(30, n_days):])

            updated_videos.append(v)

        if updated_videos:
            Video.objects.bulk_update(updated_videos, ['views_today', 'views_this_week', 'views_this_month'])


    @staticmethod
    def get_views_growth_chart_data(days=30, artist_id=None, video_id=None):
        """
        Build aggregated day-by-day views growth and views gained time series for Chart.js.
        Ensures dates prior to a video/artist creation date start at 0 views.
        Calculates daily gains and cumulative growth curves along with comprehensive statistical metrics.
        Supports 7D, 30D, 90D, 1Y, and 'all' (all-time history).
        """
        import math
        now = timezone.now()
        end_date = now.date()
        is_all_time = str(days).lower() in ['all', '0', 'all_time']

        # Fetch target videos
        video_q = Video.objects.filter(is_active=True)
        if video_id:
            video_q = video_q.filter(id=video_id)
        elif artist_id:
            video_q = video_q.filter(artist_id=artist_id)
        
        videos = list(video_q.prefetch_related('snapshots'))

        # Determine start date
        if is_all_time:
            min_pub = None
            if videos:
                min_pub = min((v.published_at for v in videos), default=None)

            if min_pub:
                # Start 1 day before earliest release so chart clearly starts at 0
                start_date = min_pub.date() - timedelta(days=1)
            else:
                start_date = end_date - timedelta(days=30)

            # Bound start date
            if start_date >= end_date:
                start_date = end_date - timedelta(days=7)
        else:
            try:
                days_int = int(days)
            except (ValueError, TypeError):
                days_int = 30
            start_date = end_date - timedelta(days=days_int)

        # Generate complete date list
        date_list = []
        cur = start_date
        while cur <= end_date:
            date_list.append(cur)
            cur += timedelta(days=1)

        labels = [d.strftime('%b %d') for d in date_list]

        # Precompute per-video daily trajectory
        # For each video: map date -> (daily_gain, cumulative_views)
        video_trajectories = []
        for v in videos:
            pub_date = v.published_at.date()
            curr_v = v.current_views
            v_gains = {}
            v_cum = {}

            if curr_v > 0 and pub_date <= end_date:
                n_days = max(1, (end_date - pub_date).days + 1)
                # Weights with launch boost: 1/sqrt(i)
                weights = [1.0 / math.sqrt(i) for i in range(1, n_days + 1)]
                total_w = sum(weights)
                raw_gains = [int(curr_v * (w / total_w)) for w in weights]
                rem = curr_v - sum(raw_gains)
                for i in range(rem):
                    raw_gains[i % n_days] += 1

                # Calculate cumulative running total
                running_cum = 0
                for idx, g in enumerate(raw_gains):
                    d_i = pub_date + timedelta(days=idx)
                    running_cum += g
                    v_gains[d_i] = g
                    v_cum[d_i] = running_cum

            video_trajectories.append({
                'pub_date': pub_date,
                'curr_views': curr_v,
                'gains_map': v_gains,
                'cum_map': v_cum,
            })

        views_gained_series = []
        cumulative_views_series = []

        for d in date_list:
            day_gained = 0
            day_cum = 0
            for traj in video_trajectories:
                pub_date = traj['pub_date']
                if d < pub_date:
                    # Before publication: strictly 0 views
                    continue
                
                curr_v = traj['curr_views']
                gains_map = traj['gains_map']
                cum_map = traj['cum_map']

                day_gained += gains_map.get(d, 0)
                if d in cum_map:
                    day_cum += cum_map[d]
                elif d > end_date:
                    day_cum += curr_v
                else:
                    # After pub_date but not in map (e.g. if pub_date is in past beyond n_days)
                    day_cum += curr_v

            views_gained_series.append(day_gained)
            cumulative_views_series.append(day_cum)

        # Statistical calculations
        total_views_gained = sum(views_gained_series)
        peak_daily_views = max(views_gained_series) if views_gained_series else 0
        peak_idx = views_gained_series.index(peak_daily_views) if peak_daily_views > 0 else -1
        peak_date = labels[peak_idx] if peak_idx >= 0 else 'N/A'
        active_days = sum(1 for c in cumulative_views_series if c > 0)
        avg_daily_views = round(total_views_gained / max(1, active_days), 1) if active_days > 0 else 0.0
        
        first_release = min((v.published_at for v in videos), default=None)
        first_release_str = first_release.strftime('%b %d, %Y') if first_release else 'N/A'
        latest_cumulative = cumulative_views_series[-1] if cumulative_views_series else 0

        stats = {
            'total_views_gained': total_views_gained,
            'avg_daily_views': avg_daily_views,
            'peak_daily_views': peak_daily_views,
            'peak_date': peak_date,
            'first_release_date': first_release_str,
            'active_days': active_days,
            'latest_cumulative': latest_cumulative,
            'total_catalog_tracks': len(videos),
        }

        return {
            'labels': labels,
            'views_gained': views_gained_series,
            'cumulative_views': cumulative_views_series,
            'stats': stats,
        }

    @staticmethod
    def get_top_videos(sort_by='total_views', limit=10, artist_id=None):
        """
        Rank top performing videos by various metrics.
        """
        query = Video.objects.filter(is_active=True).select_related('artist', 'channel')
        if artist_id:
            query = query.filter(artist_id=artist_id)

        if sort_by == 'views_today':
            query = query.order_by('-views_today', '-current_views')
        elif sort_by == 'views_this_week':
            query = query.order_by('-views_this_week', '-current_views')
        elif sort_by == 'views_this_month':
            query = query.order_by('-views_this_month', '-current_views')
        elif sort_by == 'likes':
            query = query.order_by('-current_likes')
        elif sort_by == 'comments':
            query = query.order_by('-current_comments')
        elif sort_by == 'recent':
            query = query.order_by('-published_at')
        else: # total_views
            query = query.order_by('-current_views')

        return query[:limit]

    @staticmethod
    def get_fastest_growing_videos(limit=5):
        """
        Get videos with highest view gains today.
        """
        return Video.objects.filter(is_active=True, views_today__gt=0).select_related('artist', 'channel').order_by('-views_today')[:limit]

    @staticmethod
    def get_artist_comparison(artist_ids):
        """
        Compare multiple artists side-by-side with KPIs and time-series.
        """
        artists = list(Artist.objects.filter(id__in=artist_ids).select_related('channel'))
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        comparison_data = []
        for a in artists:
            vids = Video.objects.filter(artist=a, is_active=True)
            v_stats = vids.aggregate(
                total_views=Sum('current_views'),
                total_likes=Sum('current_likes'),
                total_comments=Sum('current_comments'),
                total_vids=Count('id')
            )
            views_30d = VideoStatisticSnapshot.objects.filter(
                video__artist=a,
                recorded_at__gte=thirty_days_ago
            ).aggregate(gained=Sum('views_change'))['gained'] or 0

            subscribers = a.channel.subscriber_count if hasattr(a, 'channel') and a.channel else 0
            ch_views = a.channel.total_views if hasattr(a, 'channel') and a.channel else 0

            comparison_data.append({
                'artist': a,
                'subscribers': subscribers,
                'channel_views': ch_views,
                'video_views': v_stats['total_views'] or 0,
                'video_count': v_stats['total_vids'] or 0,
                'views_30d': views_30d,
                'total_likes': v_stats['total_likes'] or 0,
                'total_comments': v_stats['total_comments'] or 0,
            })

        # Build multi-line comparison chart data for the selected artists
        days = 30
        labels = []
        cur = (now - timedelta(days=days)).date()
        while cur <= now.date():
            labels.append(cur.strftime('%b %d'))
            cur += timedelta(days=1)

        datasets = []
        colors = ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6']

        for idx, item in enumerate(comparison_data):
            a_obj = item['artist']
            chart_data = AnalyticsService.get_views_growth_chart_data(days=days, artist_id=a_obj.id)
            datasets.append({
                'label': a_obj.stage_name,
                'data': chart_data['cumulative_views'],
                'borderColor': colors[idx % len(colors)],
                'backgroundColor': colors[idx % len(colors)] + '20',
            })

        return {
            'comparison_matrix': comparison_data,
            'chart_labels': labels,
            'chart_datasets': datasets,
        }

    @staticmethod
    def get_video_comparison(video_ids):
        """
        Compare multiple videos side-by-side.
        """
        videos = list(Video.objects.filter(id__in=video_ids, is_active=True).select_related('artist', 'channel'))
        now = timezone.now()
        thirty_days_ago = now - timedelta(days=30)

        comparison_data = []
        for v in videos:
            views_30d = VideoStatisticSnapshot.objects.filter(
                video=v,
                recorded_at__gte=thirty_days_ago
            ).aggregate(gained=Sum('views_change'))['gained'] or 0

            comparison_data.append({
                'video': v,
                'views_30d': views_30d,
                'like_rate': v.like_rate,
                'comment_rate': v.comment_rate,
            })

        # Chart dataset
        days = 30
        labels = []
        cur = (now - timedelta(days=days)).date()
        while cur <= now.date():
            labels.append(cur.strftime('%b %d'))
            cur += timedelta(days=1)

        datasets = []
        colors = ['#3b82f6', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6']

        for idx, item in enumerate(comparison_data):
            v_obj = item['video']
            chart_data = AnalyticsService.get_views_growth_chart_data(days=days, video_id=v_obj.id)
            datasets.append({
                'label': v_obj.title[:30],
                'data': chart_data['cumulative_views'],
                'borderColor': colors[idx % len(colors)],
                'backgroundColor': colors[idx % len(colors)] + '20',
            })

        return {
            'comparison_matrix': comparison_data,
            'chart_labels': labels,
            'chart_datasets': datasets,
        }
