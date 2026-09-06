import os
import tempfile
import subprocess
from django.test import TestCase, Client
from django.urls import reverse
from apps.authentication.models import User
from apps.studio.models import LongMixProject
from apps.studio.services.mix_engine import MixEngineService

class MixEngineTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='mixmaster',
            email='dj@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        self.client.force_login(self.user)

    def test_timeline_calculation(self):
        track_items = [
            {'title': 'Chill Track 1', 'artist': 'Artist A', 'duration': 180.0},
            {'title': 'Chill Track 2', 'artist': 'Artist B', 'duration': 200.0},
            {'title': 'Chill Track 3', 'artist': 'Artist C', 'duration': 150.0},
        ]
        crossfade = 6.0
        timeline, total_duration = MixEngineService.calculate_track_timeline(track_items, crossfade_seconds=crossfade)

        self.assertEqual(len(timeline), 3)
        # Track 1
        self.assertEqual(timeline[0]['start_seconds'], 0.0)
        self.assertEqual(timeline[0]['end_seconds'], 180.0)
        self.assertEqual(timeline[0]['start_time_str'], '00:00')

        # Track 2
        self.assertEqual(timeline[1]['start_seconds'], 174.0)
        self.assertEqual(timeline[1]['end_seconds'], 374.0)
        self.assertEqual(timeline[1]['start_time_str'], '02:54')

        # Track 3
        self.assertEqual(timeline[2]['start_seconds'], 368.0)
        self.assertEqual(timeline[2]['end_seconds'], 518.0)
        self.assertEqual(timeline[2]['start_time_str'], '06:08')

        self.assertEqual(total_duration, 518.0)

    def test_long_mix_project_model_properties(self):
        tracklist = [
            {'index': 1, 'title': 'Morning Sun', 'artist': 'Solar', 'start_seconds': 0.0, 'start_time_str': '00:00'},
            {'index': 2, 'title': 'Ocean Breeze', 'artist': 'Wave', 'start_seconds': 180.0, 'start_time_str': '03:00'},
            {'index': 3, 'title': 'Sunset Glow', 'artist': 'Dusk', 'start_seconds': 360.0, 'start_time_str': '06:00'},
        ]
        project = LongMixProject.objects.create(
            title='Summer Chill Continuous Mix',
            duration_seconds=540,
            track_count=3,
            tracklist_data=tracklist,
            render_status=LongMixProject.Status.COMPLETED
        )

        self.assertEqual(project.duration_formatted, '09m 00s')
        chapters = project.youtube_chapters_text
        self.assertIn('00:00 - Morning Sun (Solar)', chapters)
        self.assertIn('03:00 - Ocean Breeze (Wave)', chapters)
        self.assertIn('06:00 - Sunset Glow (Dusk)', chapters)

        desc = project.youtube_description
        self.assertIn('Summer Chill Continuous Mix', desc)
        self.assertIn('00:00 - Morning Sun', desc)

    def test_render_continuous_mix_ffmpeg(self):
        ffmpeg = MixEngineService.get_ffmpeg_binary()
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = os.path.join(tmpdir, "t1.wav")
            f2 = os.path.join(tmpdir, "t2.wav")
            out_mp3 = os.path.join(tmpdir, "blended.mp3")

            # Create 2 short sine wavs (3s each)
            subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:a', 'pcm_s16le', f1], check=True, capture_output=True)
            subprocess.run([ffmpeg, '-y', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=3', '-c:a', 'pcm_s16le', f2], check=True, capture_output=True)

            # Crossfade 1.0s -> Expected duration: 3 + 3 - 1 = 5s
            result_path = MixEngineService.render_continuous_mix([f1, f2], out_mp3, crossfade_seconds=1.0, transition_curve='qsin')
            self.assertTrue(os.path.exists(result_path))
            self.assertGreater(os.path.getsize(result_path), 5000)

            dur = MixEngineService.inspect_audio_duration(result_path)
            self.assertAlmostEqual(dur, 5.0, delta=0.5)

    def test_mix_maker_views(self):
        response = self.client.get(reverse('mix_maker'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Non-Stop Long Mix Maker")
        self.assertContains(response, "Crossfade Blend Duration")

        project = LongMixProject.objects.create(
            title='Test Long Mix',
            duration_seconds=300,
            track_count=2,
            render_status=LongMixProject.Status.COMPLETED
        )
        detail_response = self.client.get(reverse('mix_detail', args=[project.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Test Long Mix")
