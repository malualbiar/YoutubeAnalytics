from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
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
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest' or
        request.GET.get('format') == 'json' or
        'application/json' in request.headers.get('Accept', '')
    )

    if not request.user.can_manage_channels:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect('channels_list')

    try:
        sync_service = SyncService()
        log = sync_service.sync_channel(channel)
        is_success = log.status == SyncLog.Status.SUCCESS

        if is_ajax:
            return JsonResponse({
                'success': is_success,
                'channel_name': channel.channel_name,
                'new_videos': log.new_videos,
                'videos_updated': log.videos_updated,
                'duration_seconds': log.duration_seconds,
                'error_message': log.error_message if not is_success else None,
                'logs_url': '/system/logs/' if not is_success else None
            })

        if is_success:
            messages.success(request, f"Successfully synced channel '{channel.channel_name}' (+{log.new_videos} new, {log.videos_updated} updated videos in {log.duration_seconds}s).")
            return redirect(request.META.get('HTTP_REFERER') or 'channels_list')
        else:
            messages.error(request, f"Sync failed for '{channel.channel_name}': {log.error_message}")
            return redirect('sync_logs')
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e), 'logs_url': '/system/logs/'}, status=500)
        messages.error(request, f"Sync failed: {e}")
        return redirect('sync_logs')

@login_required
def trigger_sync_all_view(request):
    is_ajax = (
        request.headers.get('x-requested-with') == 'XMLHttpRequest' or
        request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest' or
        request.GET.get('format') == 'json' or
        'application/json' in request.headers.get('Accept', '')
    )

    if not request.user.can_manage_channels:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
        messages.error(request, "Permission denied.")
        return redirect(request.META.get('HTTP_REFERER') or 'channels_list')

    try:
        sync_service = SyncService()
        logs = sync_service.sync_all_channels()
        success_count = sum(1 for l in logs if l.status == SyncLog.Status.SUCCESS)
        failed_count = len(logs) - success_count
        total = len(logs)
        has_error = (failed_count > 0 and total > 0)

        if is_ajax:
            return JsonResponse({
                'success': not has_error,
                'total': total,
                'success_count': success_count,
                'failed_count': failed_count,
                'has_error': has_error,
                'message': f"Synchronization complete: {success_count} / {total} channels succeeded." if not has_error else f"Sync encountered errors on {failed_count} channel(s).",
                'logs_url': '/system/logs/' if has_error else None
            })

        if has_error:
            messages.error(request, f"Sync completed with errors on {failed_count} channel(s). View audit logs below for details.")
            return redirect('sync_logs')
        else:
            messages.success(request, f"Synchronization complete: {success_count} / {total} channels succeeded.")
            return redirect(request.META.get('HTTP_REFERER') or 'dashboard')
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e), 'logs_url': '/system/logs/'}, status=500)
        messages.error(request, f"Sync failed: {e}")
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
    quota_limit = 100000
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

        # Daily Posting & Reminders
        settings_obj.daily_posting_target = max(1, int(request.POST.get('daily_posting_target', settings_obj.daily_posting_target)))
        settings_obj.posting_reminders_enabled = request.POST.get('posting_reminders_enabled') == 'on'
        settings_obj.reminder_frequency_hours = max(1, int(request.POST.get('reminder_frequency_hours', settings_obj.reminder_frequency_hours)))
        settings_obj.reminder_start_hour = int(request.POST.get('reminder_start_hour', settings_obj.reminder_start_hour))
        settings_obj.reminder_end_hour = int(request.POST.get('reminder_end_hour', settings_obj.reminder_end_hour))

        settings_obj.save()

        messages.success(request, "System settings updated successfully.")
        return redirect('system_settings')

    return render(request, 'system/settings.html', {
        'settings': settings_obj,
    })
