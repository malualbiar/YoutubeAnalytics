import os
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.radar.services.ai_radar_service import AIRadarService
from apps.radar.services.downloader_service import AIDownloaderService
from apps.studio.models import VideoProject

User = get_user_model()


class AIRadarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testradaruser',
            email='radar@test.com',
            password='testpassword123',
            role=User.Role.SUPER_ADMIN
        )
        self.client = Client()

    @patch.object(AIRadarService, '_fetch_live_youtube_with_exact_timestamps', return_value=None)
    @patch.object(AIRadarService, '_fetch_ytdlp_date_sorted_music', return_value=None)
    def test_ai_radar_service_demo_tracks_and_velocity(self, mock_ytdlp, mock_live):
        """Test radar service returns tracks with valid velocity scores"""
        tracks = AIRadarService.get_recent_ai_music(genre='all', sort_by='velocity', force_refresh=True)
        self.assertTrue(len(tracks) > 0)
        
        first = tracks[0]
        self.assertIn('video_id', first)
        self.assertIn('title', first)
        self.assertIn('velocity_vph', first)
        self.assertIn('relative_time', first)
        self.assertIn('duration_seconds', first)
        self.assertIn('is_popular', first)

        if len(tracks) > 1:
            self.assertGreaterEqual(tracks[0]['velocity_vph'], tracks[1]['velocity_vph'])

    @patch.object(AIRadarService, '_fetch_live_youtube_with_exact_timestamps', return_value=None)
    @patch.object(AIRadarService, '_fetch_ytdlp_date_sorted_music', return_value=None)
    def test_ai_radar_service_filters(self, mock_ytdlp, mock_live):
        """Test granular time, duration, and popularity filters"""
        # Duration < 3 mins
        short_tracks = AIRadarService.get_recent_ai_music(duration='under_3', force_refresh=True)
        for t in short_tracks:
            self.assertLess(t['duration_seconds'], 180)

        # Popular channels
        pop_tracks = AIRadarService.get_recent_ai_music(popularity='popular')
        for t in pop_tracks:
            self.assertTrue(t['is_popular'])

        # Rising underground channels
        rising_tracks = AIRadarService.get_recent_ai_music(popularity='rising')
        for t in rising_tracks:
            self.assertFalse(t['is_popular'])

    def test_sanitize_filename(self):
        """Test filename sanitization removes illegal characters"""
        dirty = 'My/Awesome: Track? *Special* <AI> "Hit" | 2024'
        clean = AIDownloaderService.sanitize_filename(dirty)
        for char in ['/', ':', '?', '*', '<', '>', '"', '|']:
            self.assertNotIn(char, clean)

    def test_radar_feed_view_authenticated_with_filters(self):
        """Test radar view loads successfully with filter query params"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('radar_feed'), {
            'time': '1h',
            'duration': 'under_3',
            'popularity': 'all',
            'sort': 'velocity'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'radar/index.html')
        self.assertIn('tracks', response.context)
        self.assertIn('duration_options', response.context)
        self.assertIn('popularity_options', response.context)

    def test_radar_feed_view_unauthenticated(self):
        """Test unauthenticated user gets redirected to login"""
        response = self.client.get(reverse('radar_feed'))
        self.assertEqual(response.status_code, 302)

    @patch('apps.radar.services.downloader_service.AIDownloaderService.download_audio_file')
    def test_download_audio_view_wav(self, mock_download):
        """Test WAV audio download view returns FileResponse with correct headers"""
        dummy_wav = os.path.join(os.path.dirname(__file__), 'dummy_test.wav')
        with open(dummy_wav, 'wb') as f:
            f.write(b'RIFF....WAVEfmt ')

        response = None
        try:
            mock_download.return_value = (dummy_wav, "Test AI Beat")
            self.client.force_login(self.user)
            
            response = self.client.get(reverse('radar_download_audio'), {
                'video_id': 'kJQP7kiw5Fk',
                'format': 'wav',
                'title': 'Test AI Beat'
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'audio/wav')
            self.assertIn('attachment;', response['Content-Disposition'])
            self.assertIn('Test AI Beat.wav', response['Content-Disposition'])
        finally:
            if response is not None:
                response.close()
            if os.path.exists(dummy_wav):
                try:
                    os.remove(dummy_wav)
                except Exception:
                    pass

    def test_radar_access_denied_for_non_superadmin(self):
        """Test non-superadmin user gets redirected to dashboard"""
        viewer = User.objects.create_user(
            username='viewerradar',
            email='viewerradar@test.com',
            password='password123',
            role=User.Role.VIEWER
        )
        self.client.force_login(viewer)

        response = self.client.get(reverse('radar_feed'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        response = self.client.get(reverse('radar_download_audio'))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))

        response = self.client.post(reverse('radar_import_studio'), {})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))
