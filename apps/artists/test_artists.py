from django.test import TestCase
from django.db.utils import IntegrityError
from apps.artists.models import Artist, YouTubeChannel

class ArtistModelTests(TestCase):
    def test_artist_and_channel_creation(self):
        artist = Artist.objects.create(
            name='Test Artist',
            stage_name='Test Stage',
            genre='Pop',
            status=Artist.Status.ACTIVE
        )
        self.assertEqual(str(artist), 'Test Stage')
        self.assertFalse(artist.has_channel)

        channel = YouTubeChannel.objects.create(
            artist=artist,
            channel_id='UCtestchannel123456789012',
            channel_name='Test Channel',
            channel_url='https://youtube.com/@test',
            subscriber_count=10000,
            total_views=500000,
            video_count=12
        )
        self.assertTrue(artist.has_channel)
        self.assertEqual(artist.channel.channel_name, 'Test Channel')

    def test_duplicate_channel_prevention(self):
        artist1 = Artist.objects.create(name='Artist 1', stage_name='Artist 1')
        artist2 = Artist.objects.create(name='Artist 2', stage_name='Artist 2')

        YouTubeChannel.objects.create(
            artist=artist1,
            channel_id='UCduplicate123456789012',
            channel_name='Channel 1',
            channel_url='https://youtube.com/@ch1'
        )

        with self.assertRaises(IntegrityError):
            YouTubeChannel.objects.create(
                artist=artist2,
                channel_id='UCduplicate123456789012',  # duplicate ID
                channel_name='Channel 2',
                channel_url='https://youtube.com/@ch2'
            )

    def test_artist_detail_view_context(self):
        from apps.authentication.models import User
        from apps.videos.models import Video
        from django.utils import timezone
        from django.urls import reverse

        user = User.objects.create_superuser(
            username='tester',
            email='tester@test.com',
            password='password123',
            role=User.Role.SUPER_ADMIN
        )
        self.client.force_login(user)

        artist = Artist.objects.create(name='Artist Detail', stage_name='Artist Detail', genre='Pop')
        channel = YouTubeChannel.objects.create(
            artist=artist,
            channel_id='UCartistdetail123456789',
            channel_name='Artist Channel',
            channel_url='https://youtube.com/@detail',
            subscriber_count=5000,
            total_views=100000,
            video_count=1
        )
        video = Video.objects.create(
            youtube_video_id='viddetail123',
            artist=artist,
            channel=channel,
            title='Detail Song',
            current_views=50000,
            views_this_month=12000,
            views_today=500,
            views_this_week=3000,
            published_at=timezone.now()
        )

        response = self.client.get(reverse('artist_detail', args=[artist.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['views_this_month'], 50000)
        self.assertContains(response, "This Month's Views")
        self.assertContains(response, "50,000")

