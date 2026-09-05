from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.artists.models import YouTubeChannel
from .models import YouTubeApiUsage, SyncLog, SystemSettings
from .services.sync_service import SyncService

@login_required
def channels_list_view(request):
    channels = YouTubeChannel.objects.select_related('artist').all().order_by('-total_views')
    return render(request, 'system/channels.html', {'channels': channels})

@login_required
def trigger_sync_channel_view(request, pk):
    channel = get_object_or_404(YouTubeChannel, pk=pk)
    if not request.user.can_manage_channels:
        messages.error(request, "Permission denied.")
        return redirect('channels_list')

    sync_service = SyncService()
    log = sync_service.sync_channel(channel)
    if log.status == SyncLog.Status.SUCCESS:
        messages.success(request, f"Successfully synced channel '{channel.channel_name}' (+{log.new_videos} new, {log.videos_updated} updated videos in {log.duration_seconds}s).")
    else:
        messages.error(request, f"Sync failed for '{channel.channel_name}': {log.error_message}")

    return redirect('channels_list')

@login_required
def trigger_sync_all_view(request):
    if not request.user.can_manage_channels:
        messages.error(request, "Permission denied.")
        return redirect('channels_list')

    sync_service = SyncService()
    logs = sync_service.sync_all_channels()
    success_count = sum(1 for l in logs if l.status == SyncLog.Status.SUCCESS)
    messages.success(request, f"Synchronization complete: {success_count} / {len(logs)} channels succeeded.")
    return redirect('sync_logs')

@login_required
def sync_logs_view(request):
    logs = SyncLog.objects.select_related('channel').all()[:50]
    return render(request, 'system/sync_logs.html', {'logs': logs})

@login_required
def api_usage_view(request):
    usages = YouTubeApiUsage.objects.all()[:30]
    today_usage = usages.first() if usages else None
    
    # Calculate health status
    quota_used_today = today_usage.quota_used if today_usage else 0
    quota_limit = 10000
    quota_percent = round((quota_used_today / quota_limit) * 100, 1)

    return render(request, 'system/api_usage.html', {
        'usages': usages,
        'today_usage': today_usage,
        'quota_used_today': quota_used_today,
        'quota_limit': quota_limit,
        'quota_percent': quota_percent,
    })

@login_required
def system_settings_view(request):
    settings_obj = SystemSettings.get_settings()

    if request.method == 'POST':
        if not request.user.can_edit_settings:
            messages.error(request, "Super Admin privileges required to modify system settings.")
            return redirect('system_settings')

        settings_obj.sync_interval_hours = int(request.POST.get('sync_interval_hours', settings_obj.sync_interval_hours))
        settings_obj.app_timezone = request.POST.get('app_timezone', settings_obj.app_timezone).strip()
        settings_obj.default_reporting_period = request.POST.get('default_reporting_period', settings_obj.default_reporting_period)
        settings_obj.spike_alert_threshold = int(request.POST.get('spike_alert_threshold', settings_obj.spike_alert_threshold))
        settings_obj.save()

        messages.success(request, "System settings updated successfully.")
        return redirect('system_settings')

    return render(request, 'system/settings.html', {
        'settings': settings_obj,
    })
