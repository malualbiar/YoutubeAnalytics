from django.db import models
from apps.artists.models import YouTubeChannel
from django.utils import timezone

class YouTubeApiUsage(models.Model):
    date = models.DateField(unique=True, default=timezone.now, db_index=True)
    quota_used = models.IntegerField(default=0, help_text="Total estimated quota units consumed today (standard daily limit is 100,000)")
    request_count = models.IntegerField(default=0, help_text="Number of API requests executed")
    last_request_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date']
        verbose_name = 'YouTube API Usage'
        verbose_name_plural = 'YouTube API Usages'

    def __str__(self):
        return f"{self.date}: {self.quota_used:,} / 100,000 quota units ({self.request_count} calls)"

    @classmethod
    def record_usage(cls, units=1):
        """Record quota units used today"""
        today = timezone.now().date()
        usage, _ = cls.objects.get_or_create(date=today)
        usage.quota_used += units
        usage.request_count += 1
        usage.save()
        return usage


class SyncLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'RUNNING', 'Running'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    channel = models.ForeignKey(
        YouTubeChannel,
        on_delete=models.CASCADE,
        related_name='sync_logs',
        null=True,
        blank=True
    )
    channel_name_cached = models.CharField(max_length=255, blank=True, default='')
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    
    videos_found = models.IntegerField(default=0)
    new_videos = models.IntegerField(default=0)
    videos_updated = models.IntegerField(default=0)
    snapshots_created = models.IntegerField(default=0)
    duration_seconds = models.FloatField(default=0.0)
    error_message = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-started_at']
        verbose_name = 'Sync Log'
        verbose_name_plural = 'Sync Logs'

    def __str__(self):
        return f"Sync {self.channel_name_cached or 'All'} @ {self.started_at:%Y-%m-%d %H:%M} [{self.status}]"


class SystemSettings(models.Model):
    sync_interval_hours = models.IntegerField(default=6)
    app_timezone = models.CharField(max_length=100, default='UTC')
    default_reporting_period = models.CharField(max_length=50, default='30d')
    spike_alert_threshold = models.IntegerField(default=10000, help_text="Views gained in 24h to trigger spike alert")
    
    # Daily Posting Target & Reminder Preferences
    daily_posting_target = models.IntegerField(default=10, help_text="Daily content upload target (e.g. 10 contents/day)")
    posting_reminders_enabled = models.BooleanField(default=True, help_text="Enable desktop notification reminders")
    reminder_frequency_hours = models.IntegerField(default=3, help_text="Interval in hours between desktop reminders if target not met")
    reminder_start_hour = models.IntegerField(default=9, help_text="Earliest hour to send reminders (0-23, e.g. 9 for 9 AM)")
    reminder_end_hour = models.IntegerField(default=21, help_text="Latest hour to send reminders (0-23, e.g. 21 for 9 PM)")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'System Settings'
        verbose_name_plural = 'System Settings'

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj
