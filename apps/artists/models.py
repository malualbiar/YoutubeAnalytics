from django.db import models

class Artist(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active'
        INACTIVE = 'INACTIVE', 'Inactive'
        PENDING = 'PENDING', 'Pending Channel'

    name = models.CharField(max_length=255, help_text="Legal/Primary name")
    stage_name = models.CharField(max_length=255, db_index=True, help_text="Public Stage/Artist name")
    profile_image = models.URLField(max_length=1000, blank=True, null=True, help_text="Image or Avatar URL")
    description = models.TextField(blank=True, default='', help_text="Artist bio or notes")
    youtube_channel_id = models.CharField(max_length=100, blank=True, default='', help_text="Linked YouTube Channel ID")
    youtube_channel_url = models.URLField(max_length=500, blank=True, default='', help_text="Full YouTube Channel or Handle URL")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    genre = models.CharField(max_length=100, blank=True, default='Music')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stage_name']
        verbose_name = 'Artist'
        verbose_name_plural = 'Artists'

    def __str__(self):
        return self.stage_name or self.name

    @property
    def has_channel(self):
        return hasattr(self, 'channel') and self.channel is not None


class YouTubeChannel(models.Model):
    class SyncStatus(models.TextChoices):
        IDLE = 'IDLE', 'Idle'
        SYNCING = 'SYNCING', 'Syncing'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    artist = models.OneToOneField(
        Artist,
        on_delete=models.CASCADE,
        related_name='channel',
        help_text="The artist who owns this YouTube channel"
    )
    channel_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Official YouTube Channel ID (e.g. UCxxxxxxxxxxxxxx)"
    )
    channel_name = models.CharField(max_length=255, help_text="YouTube Channel Display Title")
    channel_url = models.URLField(max_length=500, help_text="YouTube Channel URL or Handle")
    thumbnail_url = models.URLField(max_length=1000, blank=True, default='')
    description = models.TextField(blank=True, default='')
    uploads_playlist_id = models.CharField(max_length=100, blank=True, default='', help_text="ID of the uploads playlist (UU...)")
    
    # Cumulative stats from YouTube
    subscriber_count = models.BigIntegerField(default=0, help_text="Total subscribers (approximate by YouTube)")
    total_views = models.BigIntegerField(default=0, help_text="Total channel views")
    video_count = models.IntegerField(default=0, help_text="Total uploaded videos count")
    
    last_synced_at = models.DateTimeField(null=True, blank=True)
    sync_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.IDLE)
    last_sync_error = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-total_views']
        verbose_name = 'YouTube Channel'
        verbose_name_plural = 'YouTube Channels'

    def __str__(self):
        return f"{self.channel_name} ({self.channel_id})"
