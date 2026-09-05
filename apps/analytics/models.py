from django.db import models
from django.utils import timezone
from apps.artists.models import Artist
from apps.videos.models import Video

class ContentUploadLog(models.Model):
    class Platform(models.TextChoices):
        YOUTUBE_SHORT = 'youtube_short', 'YouTube Shorts'
        YOUTUBE_VIDEO = 'youtube_video', 'YouTube Video'
        TIKTOK = 'tiktok', 'TikTok'
        INSTAGRAM_REEL = 'instagram_reel', 'Instagram Reel'
        TRACK_RELEASE = 'track_release', 'Track / Single Release'
        OTHER = 'other', 'Other Content'

    title = models.CharField(max_length=500, help_text="Title or description of the content")
    platform = models.CharField(
        max_length=50,
        choices=Platform.choices,
        default=Platform.YOUTUBE_SHORT,
        db_index=True
    )
    artist = models.ForeignKey(
        Artist,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='content_upload_logs',
        help_text="Associated artist (optional)"
    )
    video = models.ForeignKey(
        Video,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='upload_logs',
        help_text="Linked YouTube video record if auto-synced"
    )
    url = models.URLField(max_length=1000, blank=True, default='', help_text="Direct link to content (optional)")
    posted_at = models.DateTimeField(default=timezone.now, db_index=True, help_text="Time of publication / upload")
    notes = models.TextField(blank=True, default='', help_text="Optional remarks, tags, or campaign notes")
    is_auto_synced = models.BooleanField(default=False, help_text="True if automatically imported from YouTube API")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-posted_at']
        verbose_name = 'Content Upload Log'
        verbose_name_plural = 'Content Upload Logs'

    def __str__(self):
        return f"[{self.get_platform_display()}] {self.title} ({self.posted_at:%Y-%m-%d %H:%M})"
