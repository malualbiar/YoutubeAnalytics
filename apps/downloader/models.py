from django.db import models
from django.conf import settings


class DownloadJob(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        DOWNLOADING = 'DOWNLOADING', 'Downloading'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'

    class Format(models.TextChoices):
        MP3_320 = 'mp3_320', 'MP3 320kbps'
        WAV     = 'wav',     'WAV (Lossless)'

    url = models.URLField(max_length=512)
    title = models.CharField(max_length=255, blank=True)
    uploader = models.CharField(max_length=255, blank=True)
    thumbnail_url = models.URLField(max_length=512, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    format = models.CharField(max_length=20, choices=Format.choices, default=Format.MP3_320)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    output_file = models.FileField(upload_to='downloads/', blank=True, null=True)
    file_size_bytes = models.BigIntegerField(default=0)
    error_message = models.TextField(blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    progress_text = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Download Job'
        verbose_name_plural = 'Download Jobs'

    def __str__(self):
        return f"{self.title or self.url} [{self.format}] — {self.status}"

    @property
    def duration_formatted(self):
        s = self.duration_seconds
        if s <= 0:
            return '--:--'
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

    @property
    def file_size_formatted(self):
        b = self.file_size_bytes
        if b <= 0:
            return ''
        for unit in ('B', 'KB', 'MB', 'GB'):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    @property
    def is_audio(self):
        return True  # all formats are audio-only
