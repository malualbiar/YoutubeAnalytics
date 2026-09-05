from django.test import TestCase
from django.utils import timezone
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot

class VideoModelTests(TestCase):
    def setUp(self):
        self.artist = Artist.objects.create(name='Singer', stage_name='Star')
        self.channel = YouTubeChannel.objects.create(
            artist=self.artist,
            channel_id='UCchannel12345678901234',
            channel_name='Star Official',
            channel_url='https://youtube.com/@star'
        )

    def test_video_creation_and_rates(self):
        video = Video.objects.create(
            youtube_video_id='dQw4w9WgXcQ',
            channel=self.channel,
            artist=self.artist,
            title='Never Gonna Give You Up',
            published_at=timezone.now(),
            duration='3:32',
            duration_seconds=212,
            video_url='https://youtube.com/watch?v=dQw4w9WgXcQ',
            current_views=100000,
            current_likes=5000,
            current_comments=500
        )
        self.assertEqual(video.like_rate, 5.0)  # (5,000 / 100,000) * 100 = 5.0%
        self.assertEqual(video.comment_rate, 0.5)  # (500 / 100,000) * 100 = 0.5%

    def test_snapshot_delta_tracking(self):
        video = Video.objects.create(
            youtube_video_id='test1234567',
            channel=self.channel,
            artist=self.artist,
            title='Test Track',
            published_at=timezone.now(),
            video_url='https://youtube.com/watch?v=test1234567',
            current_views=10000
        )

        s1 = VideoStatisticSnapshot.objects.create(
            video=video,
            recorded_at=timezone.now(),
            views=10000,
            views_change=0
        )

        s2 = VideoStatisticSnapshot.objects.create(
            video=video,
            recorded_at=timezone.now(),
            views=15000,
            views_change=5000
        )

        self.assertEqual(s2.views_change, 5000)
        self.assertEqual(video.snapshots.count(), 2)
