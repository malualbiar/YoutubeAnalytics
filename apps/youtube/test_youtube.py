from django.test import TestCase
from apps.youtube.services.channel_service import ChannelService
from apps.youtube.services.video_service import VideoService

class YouTubeServiceTests(TestCase):
    def test_extract_identifier(self):
        service = ChannelService()
        
        # Test handle URL
        kind, val = service.extract_identifier('https://www.youtube.com/@TheWeeknd')
        self.assertEqual(kind, 'handle')
        self.assertEqual(val, '@TheWeeknd')

        # Test raw handle
        kind, val = service.extract_identifier('@DuaLipa')
        self.assertEqual(kind, 'handle')
        self.assertEqual(val, '@DuaLipa')

        # Test channel ID URL
        kind, val = service.extract_identifier('https://www.youtube.com/channel/UC1234567890123456789012')
        self.assertEqual(kind, 'id')
        self.assertEqual(val, 'UC1234567890123456789012')

        # Test raw channel ID
        kind, val = service.extract_identifier('UC1234567890123456789012')
        self.assertEqual(kind, 'id')
        self.assertEqual(val, 'UC1234567890123456789012')

    def test_parse_iso8601_duration(self):
        vservice = VideoService()

        # PT3M45S -> 3:45, 225s
        fmt, sec = vservice.parse_iso8601_duration('PT3M45S')
        self.assertEqual(fmt, '3:45')
        self.assertEqual(sec, 225)

        # PT1H2M30S -> 1:02:30, 3750s
        fmt, sec = vservice.parse_iso8601_duration('PT1H2M30S')
        self.assertEqual(fmt, '1:02:30')
        self.assertEqual(sec, 3750)

        # PT45S -> 0:45, 45s
        fmt, sec = vservice.parse_iso8601_duration('PT45S')
        self.assertEqual(fmt, '0:45')
        self.assertEqual(sec, 45)


class SyncViewsTests(TestCase):
    def setUp(self):
        from apps.authentication.models import User
        from apps.artists.models import Artist, YouTubeChannel
        self.user = User.objects.create_superuser(
            username='syncadmin',
            email='syncadmin@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        self.artist = Artist.objects.create(name='Sync Artist', stage_name='Sync Artist', genre='Afrobeats')
        self.channel = YouTubeChannel.objects.create(
            artist=self.artist,
            channel_id='UCSync123456789012345678',
            channel_name='Sync Artist Official',
            channel_url='https://youtube.com/@SyncArtist',
            subscriber_count=50000,
            total_views=1000000,
            video_count=5
        )

    def test_sync_all_ajax_success(self):
        from unittest.mock import patch
        from apps.youtube.models import SyncLog
        from django.urls import reverse

        self.client.force_login(self.user)
        dummy_log = SyncLog(
            channel=self.channel,
            status=SyncLog.Status.SUCCESS,
            new_videos=2,
            videos_updated=3,
            duration_seconds=1.5
        )

        with patch('apps.youtube.views.SyncService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.sync_all_channels.return_value = [dummy_log]

            response = self.client.get(reverse('sync_all_channels'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data['success'])
            self.assertEqual(data['success_count'], 1)
            self.assertEqual(data['failed_count'], 0)
            self.assertIsNone(data['logs_url'])

    def test_sync_all_standard_success_redirects_referer(self):
        from unittest.mock import patch
        from apps.youtube.models import SyncLog
        from django.urls import reverse

        self.client.force_login(self.user)
        dummy_log = SyncLog(
            channel=self.channel,
            status=SyncLog.Status.SUCCESS,
            new_videos=0,
            videos_updated=5,
            duration_seconds=2.0
        )

        with patch('apps.youtube.views.SyncService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.sync_all_channels.return_value = [dummy_log]

            response = self.client.get(reverse('sync_all_channels'), HTTP_REFERER='/channels/')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, '/channels/')

    def test_sync_all_failure_redirects_to_logs(self):
        from unittest.mock import patch
        from apps.youtube.models import SyncLog
        from django.urls import reverse

        self.client.force_login(self.user)
        dummy_log = SyncLog(
            channel=self.channel,
            status=SyncLog.Status.FAILED,
            error_message="Quota exceeded"
        )

        with patch('apps.youtube.views.SyncService') as mock_service_cls:
            mock_service = mock_service_cls.return_value
            mock_service.sync_all_channels.return_value = [dummy_log]

            # Standard request
            response = self.client.get(reverse('sync_all_channels'), HTTP_REFERER='/channels/')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse('sync_logs'))

            # AJAX request
            ajax_resp = self.client.get(reverse('sync_all_channels'), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
            self.assertEqual(ajax_resp.status_code, 200)
            data = ajax_resp.json()
            self.assertFalse(data['success'])
            self.assertEqual(data['logs_url'], '/system/logs/')

