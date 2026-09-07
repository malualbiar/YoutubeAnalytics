from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count, Avg, Max, Min, F, Q
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot, ChannelStatisticSnapshot
from apps.milestones.models import VideoMilestone, NotificationLog
from apps.youtube.models import SystemSettings
from .models import ContentUploadLog

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

        views_this_week = Video.objects.filter(is_active=True).aggregate(s=Sum('views_this_week'))['s'] or 0
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
        Uses recorded snapshots if deltas exist across the time window, with intelligent
        pro-rating for partial snapshot history, release date bounding, and steady catalog streaming fallback.
        """
        import math
        now = timezone.now()
        today = now.date()
        twenty_four_hours_ago = now - timedelta(days=1)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        query = Video.objects.filter(is_active=True)
        if video_ids is not None:
            if hasattr(video_ids, 'id'):
                video_ids = [video_ids.id]
            elif isinstance(video_ids, (int, str)):
                video_ids = [video_ids]
            else:
                video_ids = [v.id if hasattr(v, 'id') else v for v in video_ids]
            query = query.filter(id__in=video_ids)
        elif artist_id:
            query = query.filter(artist_id=artist_id)

        videos = list(query.prefetch_related('snapshots'))
        updated_videos = []

        for v in videos:
            curr_v = v.current_views
            pub = v.published_at.date() if v.published_at else today
            days_since_pub = max(0, (today - pub).days)

            # Snapshots analysis
            snaps = sorted(list(v.snapshots.all()), key=lambda s: s.recorded_at)

            snaps_today = [s for s in snaps if s.recorded_at >= twenty_four_hours_ago]
            snaps_week = [s for s in snaps if s.recorded_at >= seven_days_ago]
            snaps_month = [s for s in snaps if s.recorded_at >= thirty_days_ago]

            today_snaps_gain = sum(s.views_change for s in snaps_today)
            week_snaps_gain = sum(s.views_change for s in snaps_week)
            month_snaps_gain = sum(s.views_change for s in snaps_month)

            # 1. Calculate views_today
            if days_since_pub == 0:
                v_today = curr_v
            elif today_snaps_gain > 0:
                v_today = today_snaps_gain
            elif snaps:
                v_today = today_snaps_gain
            else:
                n_days = max(1, days_since_pub + 1)
                weights = [1.0 / (1.0 + 0.1 * math.sqrt(i)) for i in range(1, n_days + 1)]
                total_w = sum(weights)
                v_today = max(0, int(curr_v * (weights[-1] / total_w))) if total_w > 0 else 0

            # 2. Calculate views_this_week
            if days_since_pub <= 7:
                v_week = curr_v
            elif week_snaps_gain > 0:
                span_days = max(1, (now - snaps_week[0].recorded_at).days) if snaps_week else 7
                if span_days < 7 and span_days > 0 and len(snaps_week) > 1:
                    v_week = min(curr_v, max(week_snaps_gain, int((week_snaps_gain / span_days) * 7)))
                else:
                    v_week = week_snaps_gain
            elif snaps:
                v_week = max(v_today, week_snaps_gain)
            else:
                n_days = max(1, days_since_pub + 1)
                weights = [1.0 / (1.0 + 0.1 * math.sqrt(i)) for i in range(1, n_days + 1)]
                total_w = sum(weights)
                w_week = sum(weights[-min(7, n_days):])
                v_week = max(0, int(curr_v * (w_week / total_w))) if total_w > 0 else 0

            # 3. Calculate views_this_month
            if days_since_pub <= 30:
                # Released within 30 days: 100% of lifetime views occurred this month
                v_month = curr_v
            elif month_snaps_gain > 0:
                span_days = max(1, (now - snaps_month[0].recorded_at).days) if snaps_month else 30
                if span_days < 28 and span_days > 0 and len(snaps_month) > 1:
                    v_month = min(curr_v, max(month_snaps_gain, int((month_snaps_gain / span_days) * 30)))
                else:
                    v_month = month_snaps_gain
            elif snaps:
                v_month = max(v_week, month_snaps_gain)
            else:
                n_days = max(1, days_since_pub + 1)
                weights = [1.0 / (1.0 + 0.1 * math.sqrt(i)) for i in range(1, n_days + 1)]
                total_w = sum(weights)
                w_month = sum(weights[-min(30, n_days):])
                v_month = max(0, int(curr_v * (w_month / total_w))) if total_w > 0 else 0

            # Monotonic bounds: 0 <= views_today <= views_this_week <= views_this_month <= current_views
            v_today = min(curr_v, max(0, v_today))
            v_week = min(curr_v, max(v_today, v_week))
            v_month = min(curr_v, max(v_week, v_month))

            v.views_today = v_today
            v.views_this_week = v_week
            v.views_this_month = v_month
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
            views_30d = vids.aggregate(s=Sum('views_this_month'))['s'] or 0
            if views_30d == 0:
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
            views_30d = v.views_this_month or (
                VideoStatisticSnapshot.objects.filter(
                    video=v,
                    recorded_at__gte=thirty_days_ago
                ).aggregate(gained=Sum('views_change'))['gained'] or 0
            )

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

    @staticmethod
    def get_daily_posting_status(target_date=None):
        """
        Calculate daily content upload metrics, streak history, and 30-day activity heatmap.
        """
        now = timezone.now()
        local_now = timezone.localtime(now)
        today = target_date or local_now.date()
        
        settings = SystemSettings.get_settings()
        target = max(1, settings.daily_posting_target)

        # 1. Fetch manual upload logs for today
        manual_logs = list(ContentUploadLog.objects.filter(
            posted_at__date=today
        ).select_related('artist', 'video'))

        # 2. Fetch videos released today
        videos_today = list(Video.objects.filter(
            published_at__date=today,
            is_active=True
        ).select_related('artist', 'channel'))

        # Track linked video IDs in manual logs to avoid double-counting
        linked_video_ids = {log.video_id for log in manual_logs if log.video_id}

        today_uploads = []
        # Add manual logs
        for log in manual_logs:
            today_uploads.append({
                'id': f"log-{log.id}",
                'raw_id': log.id,
                'is_manual': True,
                'title': log.title,
                'platform': log.platform,
                'platform_display': log.get_platform_display(),
                'artist_name': log.artist.stage_name if log.artist else (log.video.artist.stage_name if log.video else 'General'),
                'artist_image': log.artist.profile_image if (log.artist and log.artist.profile_image) else '',
                'url': log.url or (log.video.video_url if log.video else ''),
                'posted_at': log.posted_at,
                'notes': log.notes,
                'thumbnail': log.video.thumbnail_url if (log.video and log.video.thumbnail_url) else '',
            })

        # Add auto-detected videos not already manually logged
        for v in videos_today:
            if v.id not in linked_video_ids:
                is_short = v.duration_seconds > 0 and v.duration_seconds <= 60
                platform = 'youtube_short' if is_short else 'youtube_video'
                platform_display = 'YouTube Shorts' if is_short else 'YouTube Video'
                today_uploads.append({
                    'id': f"vid-{v.id}",
                    'raw_id': v.id,
                    'is_manual': False,
                    'title': v.title,
                    'platform': platform,
                    'platform_display': platform_display,
                    'artist_name': v.artist.stage_name if v.artist else 'YouTube Channel',
                    'artist_image': v.artist.profile_image if (v.artist and v.artist.profile_image) else '',
                    'url': v.video_url,
                    'posted_at': v.published_at,
                    'notes': 'Auto-synced from YouTube',
                    'thumbnail': v.thumbnail_url,
                })

        # Sort today's uploads newest first
        today_uploads.sort(key=lambda x: x['posted_at'], reverse=True)

        today_count = len(today_uploads)
        remaining = max(0, target - today_count)
        progress_pct = min(100, int((today_count / target) * 100))
        is_goal_met = today_count >= target

        # 3. Calculate 30-Day Activity Heatmap & Historic Daily Counts
        # Pre-query past 60 days of data for streak calculations
        window_days = 60
        start_date = today - timedelta(days=window_days)

        historic_videos = Video.objects.filter(
            published_at__date__gte=start_date,
            published_at__date__lte=today,
            is_active=True
        ).values('published_at__date').annotate(cnt=Count('id'))
        video_counts_by_date = {item['published_at__date']: item['cnt'] for item in historic_videos}

        historic_logs = ContentUploadLog.objects.filter(
            posted_at__date__gte=start_date,
            posted_at__date__lte=today,
            video__isnull=True  # Avoid double counting
        ).values('posted_at__date').annotate(cnt=Count('id'))
        log_counts_by_date = {item['posted_at__date']: item['cnt'] for item in historic_logs}

        # Build daily totals map
        daily_totals = {}
        for d_offset in range(window_days + 1):
            d = start_date + timedelta(days=d_offset)
            if d == today:
                daily_totals[d] = today_count
            else:
                daily_totals[d] = video_counts_by_date.get(d, 0) + log_counts_by_date.get(d, 0)

        # 4. Calculate Current Streak & Best Streak
        # Current streak:
        current_streak = 0
        check_date = today
        if is_goal_met:
            current_streak += 1
            check_date = today - timedelta(days=1)
        else:
            # Check if yesterday met goal to maintain streak in progress
            check_date = today - timedelta(days=1)

        while check_date in daily_totals and daily_totals[check_date] >= target:
            current_streak += 1
            check_date -= timedelta(days=1)

        # Best streak over recorded window:
        best_streak = 0
        run_streak = 0
        sorted_dates = sorted(daily_totals.keys())
        for d in sorted_dates:
            if daily_totals[d] >= target:
                run_streak += 1
                if run_streak > best_streak:
                    best_streak = run_streak
            else:
                run_streak = 0

        best_streak = max(best_streak, current_streak)

        # 5. Build 30-Day Activity Heatmap list
        heatmap_30d = []
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            cnt = daily_totals.get(d, 0)
            heatmap_30d.append({
                'date': d.isoformat(),
                'display_date': d.strftime('%b %d'),
                'day_name': d.strftime('%a'),
                'count': cnt,
                'target': target,
                'met_goal': cnt >= target,
                'is_today': d == today,
            })

        return {
            'target': target,
            'today_count': today_count,
            'remaining': remaining,
            'progress_pct': progress_pct,
            'is_goal_met': is_goal_met,
            'current_streak': current_streak,
            'best_streak': best_streak,
            'history_30d': heatmap_30d,
            'today_uploads': today_uploads,
            'reminders_enabled': settings.posting_reminders_enabled,
            'reminder_frequency_hours': settings.reminder_frequency_hours,
            'reminder_start_hour': settings.reminder_start_hour,
            'reminder_end_hour': settings.reminder_end_hour,
        }

    @staticmethod
    def log_content_upload(title, platform='youtube_short', artist_id=None, url='', notes='', posted_at=None):
        """
        Record a manual content upload log.
        """
        artist = None
        if artist_id:
            artist = Artist.objects.filter(id=artist_id).first()

        posted_time = posted_at or timezone.now()

        log = ContentUploadLog.objects.create(
            title=title,
            platform=platform,
            artist=artist,
            url=url,
            notes=notes,
            posted_at=posted_time,
            is_auto_synced=False
        )
        return log

    @staticmethod
    def delete_content_upload(log_id):
        """
        Delete a manual content upload log.
        """
        return ContentUploadLog.objects.filter(id=log_id, is_auto_synced=False).delete()

    @classmethod
    def get_revenue_predictions(
        cls,
        base_rpm=2.50,
        growth_rate=0.05,
        shorts_multiplier=0.02,
        loop_multiplier=1.0,
        artist_id=None,
        selected_month=None,
        **kwargs
    ):
        """
        Calculates YouTube revenue forecasting & predictions across monitored artists and videos.
        Uses standard YouTube Studio revenue calculation (RPM per 1,000 views for standard tracks and shorts).
        Provides a comprehensive monthly historical & projected summary of views, likes, comments, and revenue.
        """
        base_rpm = float(base_rpm) if base_rpm is not None else 2.50
        growth_rate = float(growth_rate) if growth_rate is not None else 0.05
        shorts_multiplier = float(shorts_multiplier) if shorts_multiplier is not None else 0.02

        # 1. Fetch artists & videos (supporting artist filter)
        all_artists_list = list(Artist.objects.filter(status=Artist.Status.ACTIVE).select_related('channel').order_by('stage_name'))
        
        artist_filter_id = None
        if artist_id and str(artist_id).isdigit():
            artist_filter_id = int(artist_id)
            artists = [a for a in all_artists_list if a.id == artist_filter_id]
        else:
            artists = all_artists_list

        video_query = Video.objects.filter(is_active=True).select_related('artist', 'channel')
        if artist_filter_id:
            video_query = video_query.filter(artist_id=artist_filter_id)
        videos = list(video_query)

        # Helper to classify format and calculate video RPM
        def get_video_format_and_rpm(v):
            dur = v.duration_seconds or 0
            title_lower = (v.title or '').lower()
            if (dur > 0 and dur <= 60) or '#shorts' in title_lower or 'short' in title_lower:
                fmt = 'Shorts'
                rpm = max(0.01, round(base_rpm * shorts_multiplier, 2))
            else:
                fmt = 'Standard Track'
                rpm = round(base_rpm, 2)
            return fmt, rpm

        # 2. Process Videos
        processed_videos = []
        format_totals = {
            'Standard Track': {'views_30d': 0, 'revenue_30d': 0.0, 'count': 0},
            'Shorts': {'views_30d': 0, 'revenue_30d': 0.0, 'count': 0},
        }

        total_catalog_likes = sum(v.current_likes for v in videos)
        total_catalog_comments = sum(v.current_comments for v in videos)
        total_catalog_views = sum(v.current_views for v in videos)

        for v in videos:
            fmt, rpm = get_video_format_and_rpm(v)
            v_month_views = v.views_this_month
            v_today_views = v.views_today
            v_curr_views = v.current_views

            monthly_rev = round((v_month_views / 1000.0) * rpm, 2)
            today_rev = round((v_today_views / 1000.0) * rpm, 2)
            lifetime_rev = round((v_curr_views / 1000.0) * rpm, 2)
            annual_rev = round(monthly_rev * 12.0 * (1.0 + (growth_rate * 6)), 2)

            if fmt not in format_totals:
                format_totals[fmt] = {'views_30d': 0, 'revenue_30d': 0.0, 'count': 0}

            format_totals[fmt]['views_30d'] += v_month_views
            format_totals[fmt]['revenue_30d'] += monthly_rev
            format_totals[fmt]['count'] += 1

            processed_videos.append({
                'id': v.id,
                'title': v.title,
                'artist_id': v.artist_id,
                'artist_name': v.artist.stage_name if v.artist else 'Unknown',
                'format': fmt,
                'rpm': rpm,
                'published_at': v.published_at,
                'current_views': v_curr_views,
                'current_likes': v.current_likes,
                'current_comments': v.current_comments,
                'views_today': v_today_views,
                'views_this_month': v_month_views,
                'monthly_revenue': monthly_rev,
                'today_revenue': today_rev,
                'annual_revenue': annual_rev,
                'lifetime_revenue': lifetime_rev,
                'thumbnail_url': v.thumbnail_url or '',
            })

        processed_videos.sort(key=lambda x: x['monthly_revenue'], reverse=True)

        # 3. Process Artists
        artist_matrices = []
        total_platform_monthly_rev = sum(v['monthly_revenue'] for v in processed_videos)
        total_platform_lifetime_rev = sum(v['lifetime_revenue'] for v in processed_videos)
        total_platform_30d_views = sum(v['views_this_month'] for v in processed_videos)
        total_platform_today_views = sum(v['views_today'] for v in processed_videos)

        for a in artists:
            a_vids = [v for v in processed_videos if v['artist_id'] == a.id]
            a_month_views = sum(v['views_this_month'] for v in a_vids)
            a_lifetime_views = sum(v['current_views'] for v in a_vids)
            a_month_rev = sum(v['monthly_revenue'] for v in a_vids)
            a_today_rev = sum(v['today_revenue'] for v in a_vids)
            a_lifetime_rev = sum(v['lifetime_revenue'] for v in a_vids)
            a_annual_rev = round(a_month_rev * 12.0 * (1.0 + (growth_rate * 6)), 2)
            a_share_pct = round((a_month_rev / total_platform_monthly_rev * 100), 1) if total_platform_monthly_rev > 0 else 0.0
            a_avg_rpm = round((a_month_rev / (a_month_views / 1000.0)), 2) if a_month_views > 0 else base_rpm
            top_song = a_vids[0]['title'] if a_vids else 'N/A'

            artist_matrices.append({
                'artist': a,
                'video_count': len(a_vids),
                'lifetime_views': a_lifetime_views,
                'views_this_month': a_month_views,
                'monthly_revenue': round(a_month_rev, 2),
                'today_revenue': round(a_today_rev, 2),
                'annual_revenue': a_annual_rev,
                'lifetime_revenue': round(a_lifetime_rev, 2),
                'revenue_share_pct': a_share_pct,
                'effective_rpm': a_avg_rpm,
                'top_song': top_song,
            })

        artist_matrices.sort(key=lambda x: x['monthly_revenue'], reverse=True)

        # 4. Monthly Performance Timeline (Historical Months up to Current Month)
        now = timezone.now()
        cur_year = now.year
        cur_month = now.month
        current_month_key = now.strftime('%Y-%m')

        like_ratio = (total_catalog_likes / max(1, total_catalog_views)) if total_catalog_views > 0 else 0.05
        comment_ratio = (total_catalog_comments / max(1, total_catalog_views)) if total_catalog_views > 0 else 0.003
        top_platform_artist = artist_matrices[0]['artist'].stage_name if artist_matrices else 'N/A'
        top_platform_song = processed_videos[0]['title'] if processed_videos else 'N/A'

        monthly_summaries = []

        # Helper to construct month keys
        def get_year_month(offset_months):
            total_m = (cur_year * 12 + cur_month - 1) + offset_months
            y = total_m // 12
            m = (total_m % 12) + 1
            return y, m

        from datetime import date

        # Look back over the past 5 historical months + current month (up to 6 active months)
        for offset in range(-5, 0):
            y, m = get_year_month(offset)
            m_date = date(y, m, 1)
            m_key = m_date.strftime('%Y-%m')
            m_label = m_date.strftime('%b %Y')
            m_full = m_date.strftime('%B %Y')

            # Query snapshots in this historical month
            snap_qs = VideoStatisticSnapshot.objects.filter(
                recorded_at__year=y,
                recorded_at__month=m
            )
            if artist_filter_id:
                snap_qs = snap_qs.filter(video__artist_id=artist_filter_id)

            snaps = list(snap_qs.select_related('video', 'video__artist'))
            snap_views = sum(s.views_change for s in snaps)
            snap_likes = sum(s.likes_change for s in snaps)
            snap_comments = sum(s.comments_change for s in snaps)

            # Check new videos released in this month
            released_in_month = [v for v in videos if v.published_at and v.published_at.year == y and v.published_at.month == m]
            rel_views = sum(v.current_views for v in released_in_month)
            rel_likes = sum(v.current_likes for v in released_in_month)
            rel_comments = sum(v.current_comments for v in released_in_month)

            m_views = max(snap_views, rel_views)
            if m_views == 0 and offset >= -2 and total_platform_30d_views > 0:
                # Approximate baseline velocity for recently active catalog months
                m_views = int(total_platform_30d_views * (0.85 ** abs(offset)))

            m_likes = max(snap_likes, rel_likes, int(m_views * like_ratio))
            m_comments = max(snap_comments, rel_comments, int(m_views * comment_ratio))
            m_interactions = m_likes + m_comments
            m_int_rate = round((m_interactions / max(1, m_views)) * 100, 2)
            m_rev = round((m_views / 1000.0) * base_rpm, 2)

            top_artist_name = released_in_month[0].artist.stage_name if released_in_month and released_in_month[0].artist else top_platform_artist
            top_song_name = released_in_month[0].title if released_in_month else top_platform_song

            # Include months with activity or recent months
            monthly_summaries.append({
                'month_key': m_key,
                'month_label': m_label,
                'full_month_name': m_full,
                'is_current': False,
                'is_projected': False,
                'status': 'Historical',
                'views': m_views,
                'likes': m_likes,
                'comments': m_comments,
                'interactions': m_interactions,
                'interaction_rate': m_int_rate,
                'rpm': base_rpm,
                'revenue': m_rev,
                'formula_breakdown': f"({m_views:,} views / 1,000) × ${base_rpm:.2f} RPM = ${m_rev:,.2f}",
                'top_artist': top_artist_name,
                'top_video': top_song_name,
                'mom_growth': 0.0,
            })

        # Filter out leading zero months before activity started
        while len(monthly_summaries) > 2 and monthly_summaries[0]['views'] == 0:
            monthly_summaries.pop(0)

        # Current Month (September 2026 to Date)
        current_m_views = total_platform_30d_views
        current_m_likes = int(current_m_views * like_ratio) if current_m_views > 0 else 0
        current_m_comments = int(current_m_views * comment_ratio) if current_m_views > 0 else 0
        current_m_interactions = current_m_likes + current_m_comments
        current_m_int_rate = round((current_m_interactions / max(1, current_m_views)) * 100, 2)
        current_m_rev = total_platform_monthly_rev

        monthly_summaries.append({
            'month_key': current_month_key,
            'month_label': now.strftime('%b %Y'),
            'full_month_name': now.strftime('%B %Y'),
            'is_current': True,
            'is_projected': False,
            'status': 'Current Month',
            'views': current_m_views,
            'likes': current_m_likes,
            'comments': current_m_comments,
            'interactions': current_m_interactions,
            'interaction_rate': current_m_int_rate,
            'rpm': base_rpm,
            'revenue': current_m_rev,
            'formula_breakdown': f"({current_m_views:,} views / 1,000) × ${base_rpm:.2f} RPM = ${current_m_rev:,.2f}",
            'top_artist': top_platform_artist,
            'top_video': top_platform_song,
            'mom_growth': 0.0,
        })

        # Calculate MoM growth across all records
        for i in range(1, len(monthly_summaries)):
            prev_v = monthly_summaries[i - 1]['views']
            curr_v = monthly_summaries[i]['views']
            if prev_v > 0:
                monthly_summaries[i]['mom_growth'] = round(((curr_v - prev_v) / prev_v) * 100, 1)

        # 5. Month Filter Resolution
        selected_month_data = None
        if selected_month and selected_month != 'all':
            matched = [ms for ms in monthly_summaries if ms['month_key'] == selected_month or ms['month_label'] == selected_month]
            if matched:
                selected_month_data = matched[0]

        # 6. Platform KPIs
        effective_avg_rpm = round((total_platform_monthly_rev / (total_platform_30d_views / 1000.0)), 2) if total_platform_30d_views > 0 else base_rpm
        total_platform_daily_rev = sum(v['today_revenue'] for v in processed_videos)
        total_quarterly_projected = round(total_platform_monthly_rev * 3.0, 2)
        total_annual_projected = round(total_platform_monthly_rev * 12.0, 2)

        # 7. Chart Datasets (Actual Monthly Revenue & Views Trend)
        chart_month_labels = [ms['month_label'] for ms in monthly_summaries]
        monthly_revenue_series = [ms['revenue'] for ms in monthly_summaries]
        monthly_views_series = [ms['views'] for ms in monthly_summaries]
        monthly_interactions_series = [ms['interactions'] for ms in monthly_summaries]

        chart_colors = ['#10b981', '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b', '#14b8a6', '#6366f1', '#f43f5e']
        artist_share_labels = [item['artist'].stage_name for item in artist_matrices[:8]]
        artist_share_data = [item['monthly_revenue'] for item in artist_matrices[:8]]
        if len(artist_matrices) > 8:
            other_rev = sum(item['monthly_revenue'] for item in artist_matrices[8:])
            artist_share_labels.append('Other Artists')
            artist_share_data.append(round(other_rev, 2))

        return {
            'base_rpm': base_rpm,
            'growth_rate': growth_rate,
            'growth_rate_pct': int(growth_rate * 100),
            'shorts_multiplier': shorts_multiplier,
            'loop_multiplier': loop_multiplier,
            'selected_artist_id': artist_filter_id,
            'selected_month': selected_month or 'all',
            'selected_month_data': selected_month_data,
            'available_artists': all_artists_list,
            'monthly_summaries': monthly_summaries,
            'kpis': {
                'total_monthly_revenue': round(total_platform_monthly_rev, 2),
                'total_daily_revenue': round(total_platform_daily_rev, 2),
                'total_quarterly_projected': total_quarterly_projected,
                'total_annual_projected': total_annual_projected,
                'total_lifetime_revenue': round(total_platform_lifetime_rev, 2),
                'effective_avg_rpm': effective_avg_rpm,
                'total_30d_views': total_platform_30d_views,
                'total_today_views': total_platform_today_views,
                'top_earning_artist': top_platform_artist,
                'active_artists_count': len(artists),
                'total_videos_count': len(videos),
                'is_filtered_by_month': bool(selected_month_data),
                'filtered_month_name': selected_month_data['full_month_name'] if selected_month_data else None,
                'filtered_month_views': selected_month_data['views'] if selected_month_data else total_platform_30d_views,
                'filtered_month_revenue': selected_month_data['revenue'] if selected_month_data else total_platform_monthly_rev,
                'filtered_month_likes': selected_month_data['likes'] if selected_month_data else total_catalog_likes,
                'filtered_month_comments': selected_month_data['comments'] if selected_month_data else total_catalog_comments,
            },
            'artists': artist_matrices,
            'artist_matrix': artist_matrices,
            'top_videos': processed_videos[:25],
            'top_earning_songs': processed_videos[:25],
            'all_videos': processed_videos,
            'format_totals': format_totals,
            'chart_data': {
                'month_labels': chart_month_labels,
                'revenue_series': monthly_revenue_series,
                'views_series': monthly_views_series,
                'interactions_series': monthly_interactions_series,
                'expected_series': monthly_revenue_series,
                'artist_share_labels': artist_share_labels,
                'artist_share_data': artist_share_data,
                'chart_colors': chart_colors[:len(artist_share_labels)],
            },
            'projection_series': monthly_revenue_series,
        }

