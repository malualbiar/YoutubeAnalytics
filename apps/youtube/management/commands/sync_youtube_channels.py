from django.core.management.base import BaseCommand
from apps.youtube.services.sync_service import SyncService
from apps.artists.models import YouTubeChannel

class Command(BaseCommand):
    help = 'Sync all registered YouTube channels with live YouTube Data API v3'

    def add_arguments(self, parser):
        parser.add_argument('--channel-id', type=str, help='Sync a specific channel by YouTube Channel ID')

    def handle(self, *args, **options):
        channel_id = options.get('channel_id')
        sync_service = SyncService()

        if channel_id:
            channel = YouTubeChannel.objects.filter(channel_id=channel_id).first()
            if not channel:
                self.stderr.write(self.style.ERROR(f"Channel with ID '{channel_id}' not found."))
                return
            self.stdout.write(f"Syncing channel '{channel.channel_name}'...")
            log = sync_service.sync_channel(channel)
            if log.status == 'SUCCESS':
                self.stdout.write(self.style.SUCCESS(f"[OK] Channel '{channel.channel_name}' synced successfully ({log.duration_seconds}s, {log.videos_updated} videos updated)."))
            else:
                self.stderr.write(self.style.ERROR(f"[FAIL] Sync failed: {log.error_message}"))
        else:
            self.stdout.write("Syncing all active YouTube channels...")
            logs = sync_service.sync_all_channels()
            success = sum(1 for l in logs if l.status == 'SUCCESS')
            self.stdout.write(self.style.SUCCESS(f"[OK] Sync completed: {success}/{len(logs)} channels updated."))
