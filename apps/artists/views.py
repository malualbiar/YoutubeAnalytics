from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.http import JsonResponse
from .models import Artist, YouTubeChannel
from apps.videos.models import Video
from apps.analytics.services import AnalyticsService
from apps.youtube.services.channel_service import ChannelService
from apps.youtube.services.sync_service import SyncService
from apps.youtube.services.youtube_client import YouTubeAPIError

@login_required
def artist_list_view(request):
    search_query = request.GET.get('q', '').strip()
    genre_filter = request.GET.get('genre', '').strip()
    status_filter = request.GET.get('status', '').strip()

    artists = Artist.objects.all().select_related('channel').annotate(
        video_count_agg=Count('videos', filter=Q(videos__is_active=True)),
        total_views_agg=Sum('videos__current_views', filter=Q(videos__is_active=True))
    )

    if search_query:
        artists = artists.filter(
            Q(name__icontains=search_query) |
            Q(stage_name__icontains=search_query) |
            Q(channel__channel_name__icontains=search_query)
        )

    if genre_filter:
        artists = artists.filter(genre__iexact=genre_filter)

    if status_filter:
        artists = artists.filter(status=status_filter)

    genres = Artist.objects.values_list('genre', flat=True).distinct()

    return render(request, 'artists/list.html', {
        'artists': artists,
        'search_query': search_query,
        'genre_filter': genre_filter,
        'status_filter': status_filter,
        'genres': genres,
    })

@login_required
def artist_detail_view(request, pk):
    artist = get_object_or_404(Artist.objects.select_related('channel'), pk=pk)
    
    # Range for chart
    range_days_param = request.GET.get('days', '30')
    if range_days_param == 'all':
        range_days = 'all'
    else:
        try:
            range_days = int(range_days_param)
        except (ValueError, TypeError):
            range_days = 30

    AnalyticsService.update_video_growth_metrics(artist_id=artist.id)
    chart_data = AnalyticsService.get_views_growth_chart_data(days=range_days, artist_id=artist.id)

    # Top videos for this artist
    videos = Video.objects.filter(artist=artist, is_active=True).order_by('-current_views')
    
    # Aggregates
    stats = videos.aggregate(
        total_views=Sum('current_views'),
        total_likes=Sum('current_likes'),
        total_comments=Sum('current_comments'),
        total_count=Count('id'),
        views_this_month=Sum('views_this_month'),
        views_today=Sum('views_today'),
        views_this_week=Sum('views_this_week'),
    )

    # Channel stats
    channel = getattr(artist, 'channel', None)

    return render(request, 'artists/detail.html', {
        'artist': artist,
        'channel': channel,
        'videos': videos[:15],
        'total_videos': stats['total_count'] or 0,
        'total_views': stats['total_views'] or (channel.total_views if channel else 0),
        'total_likes': stats['total_likes'] or 0,
        'total_comments': stats['total_comments'] or 0,
        'views_this_month': stats['views_this_month'] or 0,
        'views_today': stats['views_today'] or 0,
        'views_this_week': stats['views_this_week'] or 0,
        'chart_data': chart_data,
        'range_days': range_days,
    })

@login_required
def artist_create_view(request):
    if not request.user.can_manage_artists:
        messages.error(request, "Permission denied.")
        return redirect('artist_list')

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        stage_name = request.POST.get('stage_name', '').strip() or name
        genre = request.POST.get('genre', 'Music').strip()
        description = request.POST.get('description', '').strip()
        profile_image = request.POST.get('profile_image', '').strip()
        youtube_url = request.POST.get('youtube_url', '').strip()

        if not stage_name:
            messages.error(request, "Artist name is required.")
            return render(request, 'artists/create.html')

        artist = Artist.objects.create(
            name=name or stage_name,
            stage_name=stage_name,
            genre=genre,
            description=description,
            profile_image=profile_image,
            youtube_channel_url=youtube_url,
            status=Artist.Status.ACTIVE
        )

        # If a YouTube URL was provided, attempt to connect and sync
        if youtube_url:
            try:
                ch_service = ChannelService()
                ch_data = ch_service.resolve_channel(youtube_url)
                channel, created = YouTubeChannel.objects.update_or_create(
                    channel_id=ch_data['channel_id'],
                    defaults={
                        'artist': artist,
                        'channel_name': ch_data['channel_name'],
                        'channel_url': ch_data['channel_url'],
                        'thumbnail_url': ch_data['thumbnail_url'],
                        'description': ch_data['description'],
                        'subscriber_count': ch_data['subscriber_count'],
                        'total_views': ch_data['total_views'],
                        'video_count': ch_data['video_count'],
                        'uploads_playlist_id': ch_data['uploads_playlist_id'],
                    }
                )
                artist.youtube_channel_id = channel.channel_id
                artist.youtube_channel_url = channel.channel_url
                if not artist.profile_image:
                    artist.profile_image = channel.thumbnail_url
                artist.save()

                # Trigger initial sync
                sync_service = SyncService()
                sync_service.sync_channel(channel)
                messages.success(request, f"Artist '{artist.stage_name}' created and YouTube channel '{channel.channel_name}' synced successfully!")
            except YouTubeAPIError as e:
                messages.warning(request, f"Artist created, but YouTube channel verification failed: {e}")
            except Exception as e:
                messages.warning(request, f"Artist created, but YouTube sync encountered an issue: {e}")
        else:
            messages.success(request, f"Artist '{artist.stage_name}' created successfully.")

        return redirect('artist_detail', pk=artist.id)

    return render(request, 'artists/create.html')

@login_required
def artist_edit_view(request, pk):
    artist = get_object_or_404(Artist, pk=pk)
    if not request.user.can_manage_artists:
        messages.error(request, "Permission denied.")
        return redirect('artist_detail', pk=artist.id)

    if request.method == 'POST':
        artist.name = request.POST.get('name', artist.name).strip()
        artist.stage_name = request.POST.get('stage_name', artist.stage_name).strip()
        artist.genre = request.POST.get('genre', artist.genre).strip()
        artist.description = request.POST.get('description', artist.description).strip()
        artist.profile_image = request.POST.get('profile_image', artist.profile_image).strip()
        artist.status = request.POST.get('status', artist.status)
        artist.save()
        messages.success(request, "Artist updated successfully.")
        return redirect('artist_detail', pk=artist.id)

    return render(request, 'artists/edit.html', {'artist': artist})

@login_required
def artist_delete_view(request, pk):
    artist = get_object_or_404(Artist, pk=pk)
    if not request.user.is_super_admin:
        messages.error(request, "Super Admin privileges required to delete artists.")
        return redirect('artist_detail', pk=artist.id)

    if request.method == 'POST':
        name = artist.stage_name
        artist.delete()
        messages.success(request, f"Artist '{name}' deleted.")
        return redirect('artist_list')

    return render(request, 'artists/delete_confirm.html', {'artist': artist})

@login_required
def connect_channel_view(request, pk):
    artist = get_object_or_404(Artist, pk=pk)
    if not request.user.can_manage_channels:
        messages.error(request, "Only Super Admins can connect or modify YouTube channels.")
        return redirect('artist_detail', pk=artist.id)

    if request.method == 'POST':
        channel_input = request.POST.get('channel_input', '').strip()
        if not channel_input:
            messages.error(request, "Please enter a YouTube Channel URL, Handle (e.g. @artist), or Channel ID.")
            return redirect('artist_detail', pk=artist.id)

        try:
            ch_service = ChannelService()
            ch_data = ch_service.resolve_channel(channel_input)

            # Check if channel already connected to another artist
            existing = YouTubeChannel.objects.filter(channel_id=ch_data['channel_id']).exclude(artist=artist).first()
            if existing:
                messages.error(request, f"This YouTube channel is already linked to artist '{existing.artist.stage_name}'.")
                return redirect('artist_detail', pk=artist.id)

            channel, created = YouTubeChannel.objects.update_or_create(
                artist=artist,
                defaults={
                    'channel_id': ch_data['channel_id'],
                    'channel_name': ch_data['channel_name'],
                    'channel_url': ch_data['channel_url'],
                    'thumbnail_url': ch_data['thumbnail_url'],
                    'description': ch_data['description'],
                    'subscriber_count': ch_data['subscriber_count'],
                    'total_views': ch_data['total_views'],
                    'video_count': ch_data['video_count'],
                    'uploads_playlist_id': ch_data['uploads_playlist_id'],
                }
            )

            artist.youtube_channel_id = channel.channel_id
            artist.youtube_channel_url = channel.channel_url
            if not artist.profile_image and channel.thumbnail_url:
                artist.profile_image = channel.thumbnail_url
            artist.save()

            # Trigger initial sync
            sync_service = SyncService()
            sync_service.sync_channel(channel)

            messages.success(request, f"Successfully connected and synced YouTube channel '{channel.channel_name}'!")
        except YouTubeAPIError as e:
            messages.error(request, f"YouTube validation error: {str(e)}")
        except Exception as e:
            messages.error(request, f"Unexpected error connecting channel: {str(e)}")

    return redirect('artist_detail', pk=artist.id)

@login_required
def disconnect_channel_view(request, pk):
    artist = get_object_or_404(Artist, pk=pk)
    if not request.user.can_manage_channels:
        messages.error(request, "Only Super Admins can disconnect channels.")
        return redirect('artist_detail', pk=artist.id)

    if request.method == 'POST':
        if hasattr(artist, 'channel') and artist.channel:
            ch_name = artist.channel.channel_name
            artist.channel.delete()
            artist.youtube_channel_id = ''
            artist.youtube_channel_url = ''
            artist.save()
            messages.success(request, f"Disconnected YouTube channel '{ch_name}'.")
    return redirect('artist_detail', pk=artist.id)
