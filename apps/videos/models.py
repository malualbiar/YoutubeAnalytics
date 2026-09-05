from django.db import models
from apps.artists.models import Artist, YouTubeChannel

class Video(models.Model):
    youtube_video_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="YouTube Video ID (e.g. dQw4w9WgXcQ)"
    )
    channel = models.ForeignKey(
        YouTubeChannel,
        on_delete=models.CASCADE,
        related_name='videos',
        help_text="Channel the video was uploaded to"
    )
    artist = models.ForeignKey(
        Artist,
        on_delete=models.CASCADE,
        related_name='videos',
        help_text="Artist associated with the video"
    )
    title = models.CharField(max_length=500, db_index=True)
    description = models.TextField(blank=True, default='')
    thumbnail_url = models.URLField(max_length=1000, blank=True, default='')
    published_at = models.DateTimeField(db_index=True, help_text="Release / Upload date")
    duration = models.CharField(max_length=50, blank=True, default='', help_text="ISO 8601 or HH:MM:SS format")
    duration_seconds = models.IntegerField(default=0)
    video_url = models.URLField(max_length=500)
    
    # Current public YouTube metrics
    current_views = models.BigIntegerField(default=0, db_index=True)
    current_likes = models.BigIntegerField(default=0)
    current_comments = models.BigIntegerField(default=0)
    
    # Calculated today/recent growth cache
    views_today = models.BigIntegerField(default=0)
    views_this_week = models.BigIntegerField(default=0)
    views_this_month = models.BigIntegerField(default=0)
    
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, help_text="False if video was deleted or set to private")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-current_views']
        verbose_name = 'Video'
        verbose_name_plural = 'Videos'

    def __str__(self):
        return f"{self.title} ({self.youtube_video_id})"

    @property
    def like_rate(self):
        """Calculate Like-to-View engagement percentage"""
        if self.current_views > 0:
            return round((self.current_likes / self.current_views) * 100, 2)
        return 0.0

    @property
    def comment_rate(self):
        """Calculate Comment-to-View engagement percentage"""
        if self.current_views > 0:
            return round((self.current_comments / self.current_views) * 100, 2)
        return 0.0


class VideoStatisticSnapshot(models.Model):
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='snapshots',
        db_index=True
    )
    recorded_at = models.DateTimeField(db_index=True)
    
    # Cumulative stats at the time of recording
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    
    # Delta gained since previous snapshot
    views_change = models.BigIntegerField(default=0, help_text="Estimated views gained since last snapshot")
    likes_change = models.BigIntegerField(default=0)
    comments_change = models.BigIntegerField(default=0)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['video', 'recorded_at']),
        ]
        verbose_name = 'Video Statistic Snapshot'
        verbose_name_plural = 'Video Statistic Snapshots'

    def __str__(self):
        return f"{self.video.title} @ {self.recorded_at:%Y-%m-%d %H:%M} (+{self.views_change:,} views)"


class ChannelStatisticSnapshot(models.Model):
    channel = models.ForeignKey(
        YouTubeChannel,
        on_delete=models.CASCADE,
        related_name='snapshots',
        db_index=True
    )
    recorded_at = models.DateTimeField(db_index=True)
    
    # Cumulative stats at recording time
    subscriber_count = models.BigIntegerField(default=0)
    total_views = models.BigIntegerField(default=0)
    video_count = models.IntegerField(default=0)
    
    # Deltas
    subscriber_change = models.BigIntegerField(default=0)
    view_change = models.BigIntegerField(default=0)
    video_change = models.IntegerField(default=0)

    class Meta:
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['channel', 'recorded_at']),
        ]
        verbose_name = 'Channel Statistic Snapshot'
        verbose_name_plural = 'Channel Statistic Snapshots'

    def __str__(self):
        return f"{self.channel.channel_name} @ {self.recorded_at:%Y-%m-%d %H:%M} (+{self.view_change:,} views)"
