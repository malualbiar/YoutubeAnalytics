import io
import wave
import struct
from PIL import Image
from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from apps.authentication.models import User
from apps.studio.models import VideoProject
from apps.studio.services.renderer import VideoStudioRenderer

class StudioViewsTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='admin@analytics.com',
            username='admin',
            password='adminpassword123',
            role=User.Role.SUPER_ADMIN
        )
        self.client.login(email='admin@analytics.com', password='adminpassword123')

    def test_studio_home_view(self):
        response = self.client.get(reverse('studio_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'YouTube Video Studio')
        self.assertContains(response, '1-Hour Study / Chill Loop')

    def test_studio_render_view(self):
        # Generate dummy 1-second WAV
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(struct.pack("<44100h", *([1000] * 44100)))
        wav_buf.seek(0)
        audio_file = SimpleUploadedFile('test.wav', wav_buf.read(), content_type='audio/wav')

        # Generate dummy image
        img = Image.new('RGB', (600, 600), color=(30, 60, 90))
        img_buf = io.BytesIO()
        img.save(img_buf, format='JPEG')
        img_buf.seek(0)
        image_file = SimpleUploadedFile('cover.jpg', img_buf.read(), content_type='image/jpeg')

        response = self.client.post(reverse('studio_render'), {
            'title': 'Midnight Chill Vibes',
            'video_format': VideoProject.VideoFormat.VISUALIZER,
            'audio_file': audio_file,
            'cover_image': image_file,
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        project = VideoProject.objects.filter(title='Midnight Chill Vibes').first()
        self.assertIsNotNone(project)
        self.assertEqual(project.render_status, VideoProject.Status.COMPLETED)
        self.assertTrue(bool(project.output_video))
