from django.test import TestCase
from django.utils import timezone
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot
from apps.analytics.services import AnalyticsService

class AnalyticsServiceTests(TestCase):
    def setUp(self):
        self.artist = Artist.objects.create(name='Pop Star', stage_name='PopStar', status=Artist.Status.ACTIVE)
        self.channel = YouTubeChannel.objects.create(
            artist=self.artist,
            channel_id='UCpopstar12345678901234',
            channel_name='PopStar Official',
            channel_url='https://youtube.com/@popstar',
            subscriber_count=50000,
            total_views=1500000,
            video_count=1
        )
        self.video = Video.objects.create(
            youtube_video_id='vid12345',
            channel=self.channel,
            artist=self.artist,
            title='Hit Song',
            published_at=timezone.now(),
            video_url='https://youtube.com/watch?v=vid12345',
            current_views=1500000,
            current_likes=80000,
            current_comments=4000,
            views_today=25000
        )
        VideoStatisticSnapshot.objects.create(
            video=self.video,
            recorded_at=timezone.now(),
            views=1500000,
            views_change=25000
        )

    def test_dashboard_summary_calculation(self):
        summary = AnalyticsService.get_dashboard_summary()
        self.assertEqual(summary['total_artists'], 1)
        self.assertEqual(summary['total_channels'], 1)
        self.assertEqual(summary['total_videos'], 1)
        self.assertEqual(summary['total_video_views'], 1500000)
        self.assertEqual(summary['total_subscribers'], 50000)
        self.assertEqual(summary['views_today'], 25000)

    def test_top_videos_ranking(self):
        top_vids = AnalyticsService.get_top_videos(sort_by='total_views', limit=5)
        self.assertEqual(len(top_vids), 1)
        self.assertEqual(top_vids[0].title, 'Hit Song')

    def test_growth_chart_starts_at_zero_before_release(self):
        from datetime import timedelta
        # Video was published today, so 30 days ago should be 0 views
        chart_data = AnalyticsService.get_views_growth_chart_data(days=30, video_id=self.video.id)
        
        # Earliest day (30 days ago) must have 0 cumulative views and 0 gained
        self.assertEqual(chart_data['cumulative_views'][0], 0)
        self.assertEqual(chart_data['views_gained'][0], 0)
        
        # Latest day (today) must reach full cumulative views
        self.assertEqual(chart_data['cumulative_views'][-1], 1500000)
        
        # Stats checks
        self.assertIn('stats', chart_data)
        stats = chart_data['stats']
        self.assertEqual(stats['total_views_gained'], 1500000)
        self.assertGreater(stats['avg_daily_views'], 0)
        self.assertEqual(stats['peak_daily_views'], 1500000)
        self.assertEqual(stats['total_catalog_tracks'], 1)

    def test_growth_chart_all_time(self):
        chart_data = AnalyticsService.get_views_growth_chart_data(days='all', artist_id=self.artist.id)
        # Should start at 0 on day before release
        self.assertEqual(chart_data['cumulative_views'][0], 0)
        self.assertEqual(chart_data['cumulative_views'][-1], 1500000)

    def test_revenue_predictions(self):
        predictions = AnalyticsService.get_revenue_predictions(
            base_rpm=2.00,
            growth_rate=0.05,
            shorts_multiplier=0.02
        )
        self.assertIn('kpis', predictions)
        self.assertIn('artist_matrix', predictions)
        self.assertIn('projection_series', predictions)
        self.assertIn('top_earning_songs', predictions)
        self.assertIn('monthly_summaries', predictions)
        self.assertGreater(len(predictions['monthly_summaries']), 0)
        self.assertEqual(len(predictions['artist_matrix']), 1)
        self.assertGreater(predictions['kpis']['total_today_views'], 0)
        self.assertGreater(predictions['kpis']['total_lifetime_revenue'], 0)

    def test_revenue_predictions_filtered_by_month_and_artist(self):
        predictions = AnalyticsService.get_revenue_predictions(
            base_rpm=2.50,
            artist_id=self.artist.id,
            selected_month=timezone.now().strftime('%Y-%m')
        )
        self.assertTrue(predictions['kpis']['is_filtered_by_month'])
        self.assertEqual(predictions['kpis']['filtered_month_name'], timezone.now().strftime('%B %Y'))
        self.assertEqual(len(predictions['artists']), 1)

    def test_monthly_views_recent_release(self):
        AnalyticsService.update_video_growth_metrics(self.video)
        self.video.refresh_from_db()
        # Since published today <= 30 days, views_this_month should equal current_views
        self.assertEqual(self.video.views_this_month, 1500000)



