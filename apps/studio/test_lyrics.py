import io
import json
import wave
import struct
from unittest.mock import patch
from PIL import Image
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.authentication.models import User
from apps.studio.models import LyricVideoProject
from apps.studio.services.lyrics_engine import LyricsEngineService

class LyricsStudioTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@lyrics.com',
            username='lyricsadmin',
            password='adminpassword123',
            role=User.Role.SUPER_ADMIN
        )
        self.client.login(email='admin@lyrics.com', password='adminpassword123')

        self.viewer = User.objects.create_user(
            email='viewer@lyrics.com',
            username='lyricsviewer',
            password='viewerpassword123',
            role=User.Role.VIEWER
        )

    def create_mock_audio_file(self, filename="sample.wav", duration_sec=2):
        """Creates an in-memory mono WAV file."""
        buf = io.BytesIO()
        sample_rate = 8000
        n_frames = sample_rate * duration_sec
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            raw_data = struct.pack(f'<{n_frames}h', *([0] * n_frames))
            wf.writeframes(raw_data)
        buf.seek(0)
        return SimpleUploadedFile(filename, buf.read(), content_type="audio/wav")

    def create_mock_image_file(self, filename="cover.png"):
        """Creates an in-memory PNG image."""
        buf = io.BytesIO()
        img = Image.new('RGB', (400, 400), color=(0, 200, 255))
        img.save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile(filename, buf.read(), content_type="image/png")

    # 1. Model Properties & Helpers
    def test_model_properties_and_seo(self):
        project = LyricVideoProject.objects.create(
            title="Golden Hour",
            artist_name="JVKE",
            duration_seconds=210.0,
            animation_style=LyricVideoProject.AnimationStyle.KARAOKE_WIPE,
            aspect_ratio=LyricVideoProject.AspectRatio.LANDSCAPE_16_9,
            lyrics_data=[
                {"line": "It was just two lovers", "start": 4.5, "end": 8.0},
                {"line": "Sittin' in the car", "start": 8.0, "end": 12.0}
            ]
        )

        self.assertEqual(project.duration_formatted, "03m 30s")
        self.assertIn("JVKE - Golden Hour", project.youtube_title)
        self.assertIn("Official Lyric Video", project.youtube_title)
        self.assertIn("It was just two lovers", project.youtube_description)
        self.assertIn("[00:04.50]It was just two lovers", project.lrc_content)

    def test_vertical_model_youtube_title(self):
        project = LyricVideoProject.objects.create(
            title="Shorts Hook",
            artist_name="Artist X",
            duration_seconds=30.0,
            aspect_ratio=LyricVideoProject.AspectRatio.VERTICAL_9_16,
            lyrics_data=[{"line": "Viral hit line", "start": 0.0, "end": 3.0}]
        )
        self.assertIn("#shorts", project.youtube_title)

    # 2. LRC Parser & Exporter
    def test_parse_lrc_file(self):
        lrc_text = """[ti:Test Song]
[ar:Test Artist]
[00:05.50]First line of lyrics
[00:10.00]Second line of lyrics
[00:15.80]Third line of lyrics
"""
        parsed = LyricsEngineService.parse_lrc_file(lrc_text)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]['line'], "First line of lyrics")
        self.assertEqual(parsed[0]['start'], 5.50)
        self.assertEqual(parsed[0]['end'], 10.00)
        self.assertEqual(parsed[1]['start'], 10.00)
        self.assertEqual(parsed[1]['end'], 15.80)
        self.assertEqual(parsed[2]['start'], 15.80)
        self.assertEqual(parsed[2]['end'], 20.80)

    def test_export_lrc_string(self):
        data = [
            {"line": "Line 1", "start": 3.25, "end": 6.0},
            {"line": "Line 2", "start": 6.00, "end": 10.0}
        ]
        exported = LyricsEngineService.export_lrc_string(data, title="Song A", artist="Artist B")
        self.assertIn("[ti:Song A]", exported)
        self.assertIn("[ar:Artist B]", exported)
        self.assertIn("[00:03.25]Line 1", exported)
        self.assertIn("[00:06.00]Line 2", exported)

    def test_auto_distribute_raw_lyrics(self):
        raw = "Line 1\nLine 2\nLine 3\nLine 4"
        dist = LyricsEngineService.auto_distribute_raw_lyrics(raw, total_duration=40.0)
        self.assertEqual(len(dist), 4)
        self.assertGreater(dist[0]['start'], 0.0)
        self.assertGreater(dist[1]['start'], dist[0]['start'])
        self.assertLessEqual(dist[3]['end'], 40.0)

    # 3. ASS Subtitle Script Generation
    def test_generate_ass_subtitles_styles(self):
        lyrics = [
            {"line": "Never gonna give you up", "start": 1.0, "end": 4.5},
            {"line": "Never gonna let you down", "start": 4.5, "end": 8.0}
        ]

        import tempfile
        import os

        # Test Karaoke Wipe
        with tempfile.NamedTemporaryFile(suffix='.ass', delete=False) as f:
            ass_path = f.name
        try:
            LyricsEngineService.generate_ass_subtitles(
                lyrics_data=lyrics,
                output_ass_path=ass_path,
                aspect_ratio='16:9',
                animation_style='KARAOKE_WIPE'
            )
            with open(ass_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("[Script Info]", content)
            self.assertIn("PlayResX: 1920", content)
            self.assertIn(r"{\k", content)
            self.assertIn("Never", content)
        finally:
            if os.path.exists(ass_path):
                os.remove(ass_path)

        # Test Rolling 3-Line
        with tempfile.NamedTemporaryFile(suffix='.ass', delete=False) as f:
            ass_path = f.name
        try:
            LyricsEngineService.generate_ass_subtitles(
                lyrics_data=lyrics,
                output_ass_path=ass_path,
                aspect_ratio='9:16',
                animation_style='ROLLING_3LINE'
            )
            with open(ass_path, 'r', encoding='utf-8') as f:
                content = f.read()
            self.assertIn("PlayResX: 1080", content)
            self.assertIn("PlayResY: 1920", content)
            self.assertIn(r"\pos(", content)
        finally:
            if os.path.exists(ass_path):
                os.remove(ass_path)

    # 4. Color & Time Conversions
    def test_hex_to_ass_color(self):
        ass_cyan = LyricsEngineService.hex_to_ass_color('#00E5FF', alpha=0)
        self.assertEqual(ass_cyan, '&H00FFE500&')

        ass_white = LyricsEngineService.hex_to_ass_color('#FFFFFF', alpha=0)
        self.assertEqual(ass_white, '&H00FFFFFF&')

    def test_seconds_to_ass_time(self):
        self.assertEqual(LyricsEngineService.seconds_to_ass_time(0.0), '0:00:00.00')
        self.assertEqual(LyricsEngineService.seconds_to_ass_time(65.42), '0:01:05.42')
        self.assertEqual(LyricsEngineService.seconds_to_ass_time(3661.05), '1:01:01.05')

    # 5. Views & Access Control
    def test_lyrics_maker_view_access(self):
        # Admin access
        response = self.client.get(reverse('lyrics_maker'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Synced Lyric Video Generator")
        self.assertContains(response, "Tap-To-Sync Studio")

        # Viewer forbidden
        self.client.login(email='viewer@lyrics.com', password='viewerpassword123')
        resp_viewer = self.client.get(reverse('lyrics_maker'))
        self.assertEqual(resp_viewer.status_code, 302)

    @patch('apps.studio.services.lyrics_engine.LyricsEngineService.render_lyrics_video')
    def test_lyrics_render_view(self, mock_render):
        mock_render.return_value = {'success': True, 'duration': 45.0, 'output_video': 'out.mp4'}

        audio_file = self.create_mock_audio_file("test.wav")
        cover_file = self.create_mock_image_file("test.png")
        lyrics_json = json.dumps([
            {"line": "Dancing in the dark", "start": 0.0, "end": 4.0},
            {"line": "Middle of the night", "start": 4.0, "end": 8.0}
        ])

        response = self.client.post(reverse('lyrics_render'), {
            'title': 'Dancing in the Dark',
            'artist_name': 'Neon Lights',
            'audio_file': audio_file,
            'background_image': cover_file,
            'lyrics_data': lyrics_json,
            'animation_style': 'KARAOKE_WIPE',
            'aspect_ratio': '16:9'
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        project = LyricVideoProject.objects.get(title='Dancing in the Dark')
        self.assertEqual(project.artist_name, 'Neon Lights')
        self.assertEqual(project.render_status, LyricVideoProject.Status.COMPLETED)
        self.assertEqual(len(project.lyrics_data), 2)
        mock_render.assert_called_once()

    def test_lyrics_parse_api_plain_text(self):
        response = self.client.post(reverse('lyrics_parse_api'), {
            'raw_text': "Verse 1 line\nVerse 2 line",
            'duration': 60.0
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('lyrics_data')), 2)

    def test_lyrics_export_lrc_view(self):
        project = LyricVideoProject.objects.create(
            title="Export Test",
            artist_name="Artist",
            duration_seconds=30.0,
            lyrics_data=[{"line": "Test line", "start": 5.0, "end": 10.0}]
        )

        response = self.client.get(reverse('lyrics_export_lrc', kwargs={'pk': project.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain; charset=utf-8')
        self.assertIn("attachment; filename=", response['Content-Disposition'])
        self.assertIn("[00:05.00]Test line", response.content.decode('utf-8'))

    def test_lyrics_delete_view(self):
        project = LyricVideoProject.objects.create(
            title="Delete Test",
            lyrics_data=[]
        )
        self.assertEqual(LyricVideoProject.objects.count(), 1)

        response = self.client.post(reverse('lyrics_delete', kwargs={'pk': project.id}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LyricVideoProject.objects.count(), 0)

    # 6. Vocal Frequency Alignment & Online Search
    def test_align_lyrics_with_vocal_segments(self):
        raw_lyrics = "Verse 1 line\nVerse 2 line\nChorus line 1\nChorus line 2"
        vocal_segments = [
            {'start': 5.0, 'end': 15.0, 'duration': 10.0},
            {'start': 20.0, 'end': 32.0, 'duration': 12.0}
        ]
        aligned = LyricsEngineService.align_lyrics_with_vocal_segments(raw_lyrics, vocal_segments, total_duration=40.0)
        self.assertEqual(len(aligned), 4)
        self.assertGreaterEqual(aligned[0]['start'], 5.0)
        self.assertLessEqual(aligned[1]['end'], 15.0)
        self.assertGreaterEqual(aligned[2]['start'], 20.0)
        self.assertLessEqual(aligned[3]['end'], 32.0)

    @patch('urllib.request.urlopen')
    def test_fetch_online_synced_lyrics_success(self, mock_urlopen):
        mock_response = io.BytesIO(json.dumps({
            'trackName': 'Golden Hour',
            'artistName': 'JVKE',
            'syncedLyrics': "[00:04.50]It was just two lovers\n[00:08.00]Sittin' in the car\n",
            'plainLyrics': "It was just two lovers\nSittin' in the car"
        }).encode('utf-8'))
        mock_urlopen.return_value.__enter__.return_value = mock_response

        res = LyricsEngineService.fetch_online_synced_lyrics("Golden Hour", "JVKE")
        self.assertTrue(res.get('success'))
        self.assertTrue(res.get('is_synced'))
        self.assertEqual(len(res.get('lyrics_data')), 2)
        self.assertEqual(res['lyrics_data'][0]['line'], "It was just two lovers")
        self.assertEqual(res['lyrics_data'][0]['start'], 4.5)

    def test_lyrics_vocal_sync_api_fallback_no_audio(self):
        response = self.client.post(reverse('lyrics_vocal_sync_api'), {
            'raw_text': "Line 1\nLine 2\nLine 3",
            'duration': 60.0
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertFalse(data.get('is_vocal_detected'))
        self.assertEqual(len(data.get('lyrics_data')), 3)

    @patch('apps.studio.services.lyrics_engine.LyricsEngineService.detect_vocal_segments')
    @patch('apps.studio.services.lyrics_engine.LyricsEngineService.inspect_media_duration')
    def test_lyrics_vocal_sync_api_with_audio(self, mock_dur, mock_detect):
        mock_dur.return_value = 45.0
        mock_detect.return_value = [
            {'start': 4.0, 'end': 14.0, 'duration': 10.0},
            {'start': 18.0, 'end': 30.0, 'duration': 12.0}
        ]

        audio_file = self.create_mock_audio_file("test_vocal.wav")
        response = self.client.post(reverse('lyrics_vocal_sync_api'), {
            'raw_text': "Verse 1\nVerse 2\nChorus 1\nChorus 2",
            'audio_file': audio_file,
            'duration': 45.0
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('is_vocal_detected'))
        self.assertEqual(len(data.get('lyrics_data')), 4)
        self.assertIn("vocal phrases", data.get('message'))

    @patch('apps.studio.services.lyrics_engine.LyricsEngineService.fetch_online_synced_lyrics')
    def test_lyrics_online_search_api_endpoint(self, mock_fetch):
        mock_fetch.return_value = {
            'success': True,
            'is_synced': True,
            'lyrics_data': [{'line': 'Sample', 'start': 2.0, 'end': 5.0}],
            'track_name': 'Test Song',
            'artist_name': 'Test Artist'
        }

        response = self.client.get(reverse('lyrics_online_search_api') + '?title=Test Song&artist=Test Artist')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('is_synced'))
        self.assertEqual(len(data.get('lyrics_data')), 1)

    # 7. AI Whisper Lyrics Transcription & Sync
    @patch('faster_whisper.WhisperModel')
    def test_transcribe_and_sync_with_whisper(self, mock_whisper_class):
        class MockWord:
            def __init__(self, word, start, end):
                self.word = word
                self.start = start
                self.end = end

        class MockSegment:
            def __init__(self, text, start, end, words):
                self.text = text
                self.start = start
                self.end = end
                self.words = words

        class MockInfo:
            language = 'en'
            language_probability = 0.98
            duration = 30.0

        mock_instance = mock_whisper_class.return_value
        mock_instance.transcribe.return_value = (
            [
                MockSegment(
                    "Starlight in the evening sky",
                    2.5,
                    6.0,
                    [
                        MockWord("Starlight", 2.5, 3.2),
                        MockWord("in", 3.2, 3.5),
                        MockWord("the", 3.5, 3.8),
                        MockWord("evening", 3.8, 4.8),
                        MockWord("sky", 4.8, 6.0)
                    ]
                )
            ],
            MockInfo()
        )

        audio_file = self.create_mock_audio_file("ai_song.wav")
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tf:
            tf.write(audio_file.read())
            temp_path = tf.name

        try:
            res = LyricsEngineService.transcribe_and_sync_with_whisper(temp_path, model_size='base')
            self.assertTrue(res['success'])
            self.assertEqual(len(res['lyrics_data']), 1)
            self.assertEqual(res['lyrics_data'][0]['line'], "Starlight in the evening sky")
            self.assertEqual(res['lyrics_data'][0]['start'], 2.5)
            self.assertEqual(len(res['lyrics_data'][0]['words']), 5)
            self.assertEqual(res['detected_language'], 'en')
        finally:
            import os
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch('apps.studio.services.lyrics_engine.LyricsEngineService.transcribe_and_sync_with_whisper')
    def test_lyrics_ai_transcribe_api_endpoint(self, mock_transcribe):
        mock_transcribe.return_value = {
            'success': True,
            'lyrics_data': [
                {'line': 'AI generated vocal line', 'start': 1.0, 'end': 4.0, 'words': []}
            ],
            'plain_lyrics': 'AI generated vocal line',
            'detected_language': 'en',
            'duration': 30.0
        }

        audio_file = self.create_mock_audio_file("test_ai.wav")
        response = self.client.post(reverse('lyrics_ai_transcribe_api'), {
            'audio_file': audio_file,
            'model_size': 'base'
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('lyrics_data')), 1)
        self.assertIn("AI generated vocal line", data.get('plain_lyrics'))


