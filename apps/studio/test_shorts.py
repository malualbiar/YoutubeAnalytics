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
from apps.studio.models import ShortVideoProject
from apps.studio.services.shorts_engine import ShortsEngineService

class ShortVideoProjectTestCase(TestCase):

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email='admin@shorts.com',
            username='shortsadmin',
            password='adminpassword123',
            role=User.Role.SUPER_ADMIN
        )
        self.client.login(email='admin@shorts.com', password='adminpassword123')

        self.viewer = User.objects.create_user(
            email='viewer@shorts.com',
            username='shortsviewer',
            password='viewerpassword123',
            role=User.Role.VIEWER
        )

    def test_model_properties_and_seo(self):
        project = ShortVideoProject.objects.create(
            title="Aesthetic Vibes",
            duration_seconds=95.0,
            chop_count=3,
            chops_data=[
                {"id": 1, "title": "Part 1", "hook_text": "Wait for 0:15... 🎧", "start_seconds": 0.0, "end_seconds": 30.0, "duration": 30.0, "status": "COMPLETED"},
                {"id": 2, "title": "Part 2", "hook_text": "Insane drop! 🔥", "start_seconds": 30.0, "end_seconds": 60.0, "duration": 30.0, "status": "COMPLETED"},
                {"id": 3, "title": "Part 3", "hook_text": "Outro vibe", "start_seconds": 60.0, "end_seconds": 95.0, "duration": 35.0, "status": "COMPLETED"},
            ]
        )

        self.assertEqual(project.duration_formatted, "01m 35s")
        self.assertEqual(project.completed_chops_count, 3)
        self.assertIn("Part 1", project.youtube_title_for_chop(0))
        self.assertIn("Wait for 0:15", project.youtube_title_for_chop(0))
        self.assertIn("#shorts", project.youtube_description_for_chop(0))

    def test_generate_chop_splits(self):
        chops = ShortsEngineService.generate_chop_splits(total_duration=45.0, interval_seconds=15.0)
        self.assertEqual(len(chops), 3)
        self.assertEqual(chops[0]['start_seconds'], 0.0)
        self.assertEqual(chops[0]['end_seconds'], 15.0)
        self.assertEqual(chops[1]['start_seconds'], 15.0)
        self.assertEqual(chops[1]['end_seconds'], 30.0)
        self.assertEqual(chops[2]['start_seconds'], 30.0)
        self.assertEqual(chops[2]['end_seconds'], 45.0)

    def test_prepare_overlay_banner(self):
        img = ShortsEngineService.prepare_overlay_banner(
            hook_text="Wait for the drop! 🔥",
            part_label="Part 1",
            theme="VIRAL_HOOK",
            width=1080,
            height=1920
        )
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (1080, 1920))
        self.assertEqual(img.mode, 'RGBA')

    def test_shorts_maker_view(self):
        response = self.client.get(reverse('shorts_maker'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shorts Maker")
        self.assertContains(response, "Interactive Timeline")

    @patch.object(ShortsEngineService, 'render_video_chop')
    @patch.object(ShortsEngineService, 'inspect_media_duration', return_value=45.0)
    def test_shorts_render_view_success(self, mock_duration, mock_render_chop):
        # Create dummy video file
        dummy_video = SimpleUploadedFile("sample.mp4", b"fake mp4 video bytes", content_type="video/mp4")

        chops_payload = [
            {"id": 1, "title": "Part 1", "hook_text": "Intro Hook", "start_seconds": 0.0, "end_seconds": 15.0, "duration": 15.0},
            {"id": 2, "title": "Part 2", "hook_text": "Climax", "start_seconds": 15.0, "end_seconds": 30.0, "duration": 15.0},
        ]

        response = self.client.post(reverse('shorts_render'), {
            'title': 'Viral Drum Solo',
            'source_type': 'VIDEO',
            'source_video': dummy_video,
            'aspect_mode': 'BLURRED_FIT',
            'theme_style': 'VIRAL_HOOK',
            'chops_json': json.dumps(chops_payload),
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        project = ShortVideoProject.objects.filter(title='Viral Drum Solo').first()
        self.assertIsNotNone(project)
        self.assertEqual(project.render_status, ShortVideoProject.Status.COMPLETED)
        self.assertEqual(project.chop_count, 2)
        self.assertEqual(mock_render_chop.call_count, 2)

    def test_shorts_detail_and_delete_view(self):
        project = ShortVideoProject.objects.create(
            title="Guitar Solo Clips",
            duration_seconds=30.0,
            chop_count=2,
            chops_data=[
                {"id": 1, "title": "Part 1", "start_seconds": 0.0, "end_seconds": 15.0, "duration": 15.0, "status": "COMPLETED", "output_file": "part1.mp4", "output_url": "/media/part1.mp4"},
                {"id": 2, "title": "Part 2", "start_seconds": 15.0, "end_seconds": 30.0, "duration": 15.0, "status": "COMPLETED", "output_file": "part2.mp4", "output_url": "/media/part2.mp4"},
            ]
        )

        # Detail view
        res = self.client.get(reverse('shorts_detail', kwargs={'pk': project.id}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Guitar Solo Clips")
        self.assertContains(res, "Part 1")
        self.assertContains(res, "Part 2")

        # Export zip view
        res_zip = self.client.get(reverse('shorts_export_zip', kwargs={'pk': project.id}))
        self.assertEqual(res_zip.status_code, 200)
        self.assertEqual(res_zip['Content-Type'], 'application/zip')

        # Delete view
        del_res = self.client.post(reverse('shorts_delete', kwargs={'pk': project.id}), follow=True)
        self.assertEqual(del_res.status_code, 200)
        self.assertFalse(ShortVideoProject.objects.filter(pk=project.id).exists())

    def test_permissions_denied_for_non_admin(self):
        self.client.force_login(self.viewer)

        res_maker = self.client.get(reverse('shorts_maker'))
        self.assertEqual(res_maker.status_code, 302)
        self.assertRedirects(res_maker, reverse('dashboard'))

        res_render = self.client.post(reverse('shorts_render'), {})
        self.assertEqual(res_render.status_code, 302)
        self.assertRedirects(res_render, reverse('dashboard'))
