from django.db import models
from apps.videos.models import Video

class VideoMilestone(models.Model):
    class MilestoneType(models.TextChoices):
        VIEWS_10K = 'VIEWS_10K', '10,000 Views'
        VIEWS_50K = 'VIEWS_50K', '50,000 Views'
        VIEWS_100K = 'VIEWS_100K', '100,000 Views'
        VIEWS_250K = 'VIEWS_250K', '250,000 Views'
        VIEWS_500K = 'VIEWS_500K', '500,000 Views'
        VIEWS_1M = 'VIEWS_1M', '1,000,000 Views'
        VIEWS_5M = 'VIEWS_5M', '5,000,000 Views'
        VIEWS_10M = 'VIEWS_10M', '10,000,000 Views'
        CUSTOM = 'CUSTOM', 'Custom Milestone'

    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        related_name='milestones'
    )
    milestone_type = models.CharField(max_length=50, choices=MilestoneType.choices)
    threshold = models.BigIntegerField(help_text="Target view count reached")
    views_at_milestone = models.BigIntegerField(default=0)
    reached_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-reached_at']
        unique_together = ('video', 'threshold')
        verbose_name = 'Video Milestone'
        verbose_name_plural = 'Video Milestones'

    def __str__(self):
        return f"🎉 {self.video.title} reached {self.threshold:,} views"


class NotificationLog(models.Model):
    class NotificationType(models.TextChoices):
        MILESTONE = 'MILESTONE', 'Milestone Reached'
        SPIKE_ALERT = 'SPIKE_ALERT', 'Growth Spike Alert'
        SYNC_ERROR = 'SYNC_ERROR', 'Sync Failure'
        SYSTEM = 'SYSTEM', 'System Alert'

    notification_type = models.CharField(max_length=50, choices=NotificationType.choices, default=NotificationType.SYSTEM)
    title = models.CharField(max_length=255)
    message = models.TextField()
    link = models.CharField(max_length=500, blank=True, default='')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Notification'
        verbose_name_plural = 'Notifications'

    def __str__(self):
        return f"[{self.get_notification_type_display()}] {self.title}"
