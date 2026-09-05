from datetime import timedelta
from django.test import TestCase, Client
from django.utils import timezone
from django.urls import reverse
from apps.authentication.models import User
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video
from apps.youtube.models import SystemSettings
from apps.analytics.models import ContentUploadLog
from apps.analytics.services import AnalyticsService

class DailyContentQuotaTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='testadmin',
            email='testadmin@analytics.com',
            password='password123'
        )
        self.client.login(username='testadmin@analytics.com', password='password123')

        self.artist = Artist.objects.create(
            name='Nova Test',
            stage_name='Nova Sound',
            genre='Electronic'
        )
        self.channel = YouTubeChannel.objects.create(
            artist=self.artist,
            channel_id='UC_TEST_CHANNEL_1',
            channel_name='Nova Sound Official'
        )

        self.settings = SystemSettings.get_settings()
        self.settings.daily_posting_target = 10
        self.settings.posting_reminders_enabled = True
        self.settings.reminder_frequency_hours = 3
        self.settings.save()

    def test_default_status_zero_uploads(self):
        status = AnalyticsService.get_daily_posting_status()
        self.assertEqual(status['target'], 10)
        self.assertEqual(status['today_count'], 0)
        self.assertEqual(status['remaining'], 10)
        self.assertEqual(status['progress_pct'], 0)
        self.assertFalse(status['is_goal_met'])
        self.assertEqual(len(status['history_30d']), 30)

    def test_manual_log_content_upload(self):
        log = AnalyticsService.log_content_upload(
            title='Morning Teaser Short #1',
            platform='youtube_short',
            artist_id=self.artist.id,
            url='https://youtube.com/shorts/test1',
            notes='First post of the day'
        )
        self.assertIsNotNone(log.id)
        self.assertEqual(log.platform, 'youtube_short')

        status = AnalyticsService.get_daily_posting_status()
        self.assertEqual(status['today_count'], 1)
        self.assertEqual(status['remaining'], 9)
        self.assertEqual(status['progress_pct'], 10)
        self.assertFalse(status['is_goal_met'])
        self.assertEqual(len(status['today_uploads']), 1)

    def test_goal_completion_and_streak(self):
        now = timezone.now()
        yesterday = now - timedelta(days=1)

        # Create 10 uploads for yesterday
        for i in range(10):
            ContentUploadLog.objects.create(
                title=f'Yesterday Post {i}',
                platform='youtube_short',
                artist=self.artist,
                posted_at=yesterday
            )

        # Before today's posts, streak should be 1 (since yesterday met goal)
        status = AnalyticsService.get_daily_posting_status()
        self.assertEqual(status['current_streak'], 1)

        # Add 10 posts for today to hit today's target
        for i in range(10):
            ContentUploadLog.objects.create(
                title=f'Today Post {i}',
                platform='youtube_short',
                artist=self.artist,
                posted_at=now
            )

        status = AnalyticsService.get_daily_posting_status()
        self.assertEqual(status['today_count'], 10)
        self.assertEqual(status['remaining'], 0)
        self.assertEqual(status['progress_pct'], 100)
        self.assertTrue(status['is_goal_met'])
        self.assertEqual(status['current_streak'], 2)
        self.assertEqual(status['best_streak'], 2)

    def test_auto_synced_video_counted_today(self):
        now = timezone.now()
        Video.objects.create(
            youtube_video_id='AUTO_VID_001',
            channel=self.channel,
            artist=self.artist,
            title='Official Music Video',
            published_at=now,
            duration_seconds=180,
            video_url='https://youtube.com/watch?v=AUTO_VID_001',
            current_views=500
        )

        status = AnalyticsService.get_daily_posting_status()
        self.assertEqual(status['today_count'], 1)
        self.assertEqual(status['today_uploads'][0]['platform_display'], 'YouTube Video')

    def test_delete_manual_content_upload(self):
        log = AnalyticsService.log_content_upload(
            title='To be deleted',
            platform='tiktok'
        )
        self.assertEqual(ContentUploadLog.objects.count(), 1)
        AnalyticsService.delete_content_upload(log.id)
        self.assertEqual(ContentUploadLog.objects.count(), 0)

    def test_api_endpoint(self):
        AnalyticsService.log_content_upload(title='API Test Upload', platform='instagram_reel')
        response = self.client.get(reverse('daily_posting_status_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['target'], 10)
        self.assertEqual(data['today_count'], 1)
        self.assertEqual(len(data['today_uploads']), 1)
        self.assertTrue(data['reminders_enabled'])

    def test_post_log_form_submission(self):
        response = self.client.post(reverse('log_content_upload'), {
            'title': 'New Release Drop #9',
            'platform': 'track_release',
            'artist_id': self.artist.id,
            'url': 'https://spotify.com/album/test',
            'notes': 'Midnight drop'
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContentUploadLog.objects.filter(title='New Release Drop #9').count(), 1)

    def test_system_settings_update(self):
        response = self.client.post(reverse('system_settings'), {
            'sync_interval_hours': '6',
            'app_timezone': 'UTC',
            'default_reporting_period': '30d',
            'spike_alert_threshold': '15000',
            'daily_posting_target': '15',
            'posting_reminders_enabled': 'on',
            'reminder_frequency_hours': '2',
            'reminder_start_hour': '8',
            'reminder_end_hour': '22',
        })
        self.assertEqual(response.status_code, 302)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.daily_posting_target, 15)
        self.assertTrue(self.settings.posting_reminders_enabled)
        self.assertEqual(self.settings.reminder_frequency_hours, 2)
        self.assertEqual(self.settings.reminder_start_hour, 8)
        self.assertEqual(self.settings.reminder_end_hour, 22)
