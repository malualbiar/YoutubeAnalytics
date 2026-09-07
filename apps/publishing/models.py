import json
import logging
from django.db import models
from django.utils import timezone
from apps.artists.models import YouTubeChannel

logger = logging.getLogger(__name__)

class YouTubeOAuthAccount(models.Model):
    """
    Stores authenticated Google/YouTube OAuth 2.0 channel accounts for publishing.
    """
    linked_channel = models.ForeignKey(
        YouTubeChannel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='oauth_accounts',
        help_text="Linked YouTube Channel in the Analytics database (if matched)"
    )
    channel_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Official YouTube Channel ID (e.g. UCxxxxxxxxxxxxxx)"
    )
    channel_title = models.CharField(max_length=255, help_text="Channel name")
    channel_custom_url = models.CharField(max_length=255, blank=True, default='', help_text="Channel handle or custom URL (e.g. @artist)")
    thumbnail_url = models.URLField(max_length=1000, blank=True, default='')
    subscriber_count = models.BigIntegerField(default=0)
    video_count = models.IntegerField(default=0)

    token_json = models.JSONField(
        default=dict,
        help_text="OAuth 2.0 tokens (access_token, refresh_token, client_id, client_secret, token_uri, scopes)"
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'channel_title']
        verbose_name = 'YouTube OAuth Account'
        verbose_name_plural = 'YouTube OAuth Accounts'

    def __str__(self):
        default_str = " ★ [Default]" if self.is_default else ""
        return f"{self.channel_title} ({self.channel_id}){default_str}"

    def get_credentials(self):
        """
        Builds google.oauth2.credentials.Credentials and auto-refreshes if needed.
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        data = self.token_json or {}
        if not data:
            raise ValueError("No OAuth token data stored for this account.")

        creds = Credentials(
            token=data.get('access_token'),
            refresh_token=data.get('refresh_token'),
            token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=data.get('client_id'),
            client_secret=data.get('client_secret'),
            scopes=data.get('scopes', [
                'https://www.googleapis.com/auth/youtube.upload',
                'https://www.googleapis.com/auth/youtube.readonly',
                'https://www.googleapis.com/auth/youtube.force-ssl'
            ])
        )

        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Update saved access token
                data['access_token'] = creds.token
                self.token_json = data
                self.save(update_fields=['token_json', 'updated_at'])
            except Exception as e:
                logger.error(f"Failed to refresh YouTube OAuth token for {self.channel_title}: {e}")
                raise

        return creds

    def save(self, *args, **kwargs):
        # Ensure only one default account
        if self.is_default:
            YouTubeOAuthAccount.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        elif not YouTubeOAuthAccount.objects.filter(is_default=True).exclude(pk=self.pk).exists():
            self.is_default = True
        super().save(*args, **kwargs)


class PublishingJob(models.Model):
    """
    Tracks video upload jobs, draft submissions, scheduled releases, and direct publishing.
    """
    class PrivacyStatus(models.TextChoices):
        PRIVATE_DRAFT = 'private', 'Private Draft (Recommended)'
        UNLISTED = 'unlisted', 'Unlisted (Shareable Preview Link)'
        PUBLIC = 'public', 'Public (Instant Release)'
        SCHEDULED = 'scheduled', 'Scheduled Release'

    class Status(models.TextChoices):
        QUEUED = 'QUEUED', 'Queued'
        UPLOADING = 'UPLOADING', 'Uploading'
        PROCESSING = 'PROCESSING', 'Processing'
        SUCCESS = 'SUCCESS', 'Completed / Published'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    class SourceType(models.TextChoices):
        LONG_MIX = 'LONG_MIX', 'Non-Stop Long Mix'
        SHORT_VIDEO = 'SHORT_VIDEO', 'Viral Short / Clip'
        LYRIC_VIDEO = 'LYRIC_VIDEO', 'Synced Lyrics Video'
        VIDEO_LOOP = 'VIDEO_LOOP', '1-Hour Study / Chill Loop'
        CUSTOM_FILE = 'CUSTOM_FILE', 'Custom Media Upload'

    class UploadEngine(models.TextChoices):
        API_V3 = 'API_V3', 'YouTube Data API v3 (Official API)'
        BROWSER_AUTOMATION = 'BROWSER_AUTOMATION', 'Browser Automation (Zero Quota)'
        STUDIO_DISPATCHER = 'STUDIO_DISPATCHER', '1-Click Studio Assistant (Clipboard)'

    account = models.ForeignKey(
        YouTubeOAuthAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='jobs',
        help_text="Target YouTube channel account"
    )

    upload_engine = models.CharField(
        max_length=30,
        choices=UploadEngine.choices,
        default=UploadEngine.API_V3,
        help_text="Engine / protocol used to upload video to YouTube"
    )

    # Video Metadata
    title = models.CharField(max_length=100, help_text="YouTube video title (max 100 characters)")
    description = models.TextField(blank=True, default='', help_text="YouTube video description (max 5,000 characters)")
    tags = models.JSONField(default=list, blank=True, help_text="List of keyword tags")
    category_id = models.CharField(max_length=10, default='10', help_text="YouTube Category ID (10=Music, 24=Entertainment, 22=People & Blogs)")
    
    privacy_status = models.CharField(
        max_length=20,
        choices=PrivacyStatus.choices,
        default=PrivacyStatus.PRIVATE_DRAFT
    )
    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Scheduled release timestamp (UTC). Required if privacy_status is SCHEDULED"
    )
    made_for_kids = models.BooleanField(default=False)
    embeddable = models.BooleanField(default=True)

    # Files
    video_file_path = models.CharField(max_length=1000, help_text="Absolute local filesystem path to the .mp4 video")
    thumbnail_path = models.CharField(max_length=1000, blank=True, default='', help_text="Optional local path to custom thumbnail image")

    # Source Tracking
    source_type = models.CharField(max_length=30, choices=SourceType.choices, default=SourceType.CUSTOM_FILE)
    source_id = models.IntegerField(null=True, blank=True, help_text="ID of the Studio project in Django database")
    source_chop_index = models.IntegerField(null=True, blank=True, help_text="Chop/part index if source is a Short video project")

    # Execution State
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    progress_percent = models.IntegerField(default=0)
    bytes_uploaded = models.BigIntegerField(default=0)
    total_bytes = models.BigIntegerField(default=0)

    # YouTube Output
    youtube_video_id = models.CharField(max_length=50, blank=True, default='', db_index=True)
    youtube_url = models.URLField(max_length=500, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    retry_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Publishing Job'
        verbose_name_plural = 'Publishing Jobs'

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title} ({self.get_privacy_status_display()})"

    @property
    def youtube_studio_url(self):
        if self.youtube_video_id:
            return f"https://studio.youtube.com/video/{self.youtube_video_id}/edit"
        return None

    @property
    def youtube_watch_url(self):
        if self.youtube_video_id:
            if self.source_type == self.SourceType.SHORT_VIDEO:
                return f"https://www.youtube.com/shorts/{self.youtube_video_id}"
            return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
        return None

    @property
    def is_active(self):
        return self.status in [self.Status.QUEUED, self.Status.UPLOADING, self.Status.PROCESSING]
