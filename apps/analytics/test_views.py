from django.test import TestCase, Client
from django.urls import reverse
from apps.authentication.models import User
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video
from django.utils import timezone

class ViewRoutingAndTemplateTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        self.artist = Artist.objects.create(name='Luna Vance', stage_name='Luna Vance', genre='Pop')
        self.channel = YouTubeChannel.objects.create(
            artist=self.artist,
            channel_id='UCLunaVance123456789012',
            channel_name='Luna Vance Official',
            channel_url='https://youtube.com/@LunaVance',
            subscriber_count=100000,
            total_views=5000000,
            video_count=1
        )
        self.video = Video.objects.create(
            youtube_video_id='vid999',
            channel=self.channel,
            artist=self.artist,
            title='Midnight Track',
            published_at=timezone.now(),
            video_url='https://youtube.com/watch?v=vid999',
            current_views=5000000
        )

    def test_unauthenticated_redirects_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    def test_authenticated_dashboard_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Executive Analytics Dashboard')

    def test_artist_list_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('artist_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Luna Vance')

    def test_artist_detail_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('artist_detail', args=[self.artist.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Luna Vance')

    def test_video_list_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('video_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Midnight Track')

    def test_video_detail_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('video_detail', args=[self.video.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Midnight Track')

    def test_comparisons_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('artist_comparison'))
        self.assertEqual(response.status_code, 200)

        response_v = self.client.get(reverse('video_comparison'))
        self.assertEqual(response_v.status_code, 200)

    def test_reports_page_and_csv_export(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)

        csv_response = self.client.get(reverse('export_report_csv'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response['Content-Type'], 'text/csv')

    def test_revenue_prediction_page_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('revenue_prediction'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Monthly Revenue')
        self.assertIn('forecast', response.context)
        self.assertIn('artists', response.context['forecast'])
        self.assertIn('monthly_summaries', response.context)

    def test_revenue_prediction_with_filters(self):
        self.client.force_login(self.user)
        cur_m = timezone.now().strftime('%Y-%m')
        response = self.client.get(f"{reverse('revenue_prediction')}?artist={self.artist.id}&month={cur_m}&rpm=3.20&growth=0.08")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['base_rpm'], 3.20)
        self.assertEqual(response.context['selected_month'], cur_m)

    def test_revenue_csv_export(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('export_revenue_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Luna Vance', response.content.decode('utf-8'))
        self.assertIn('MONTHLY PERFORMANCE', response.content.decode('utf-8'))


    def test_global_search_api(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('global_search_api') + '?q=Luna')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data['artists']), 0)
        self.assertEqual(data['artists'][0]['name'], 'Luna Vance')


