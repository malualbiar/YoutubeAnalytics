import os
import shutil
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.core.files import File
from django.http import JsonResponse
from .models import VideoProject, LongMixProject
from .services.renderer import VideoStudioRenderer
from .services.mix_engine import MixEngineService
from apps.videos.models import Video

@login_required
def studio_home_view(request):
    """
    Main YouTube Video Studio dashboard: displays both 1-Hour Loops and Non-Stop Long Mixes.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    tab = request.GET.get('tab', 'mixes')
    single_loops = VideoProject.objects.all().order_by('-created_at')
    mix_projects = LongMixProject.objects.all().order_by('-created_at')
    
    total_mix_duration = sum(m.duration_seconds for m in mix_projects)
    total_loop_duration = sum(p.duration_seconds for p in single_loops)
    total_hours_produced = round((total_mix_duration + total_loop_duration) / 3600, 1)

    return render(request, 'studio/index.html', {
        'tab': tab,
        'projects': single_loops,
        'mix_projects': mix_projects,
        'total_hours_produced': total_hours_produced,
        'format_choices': VideoProject.VideoFormat.choices,
    })


@login_required
@require_POST
def studio_render_view(request):
    """
    Handles single video loop rendering form submission.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    title = request.POST.get('title', '').strip() or 'My YouTube Chill Loop'
    video_format = request.POST.get('video_format', VideoProject.VideoFormat.ONE_HOUR_LOOP)
    audio_file = request.FILES.get('audio_file')
    cover_image = request.FILES.get('cover_image')

    if not audio_file:
        messages.error(request, "Please upload an audio file (.wav or .mp3).")
        return redirect('studio_home')

    if not cover_image:
        messages.error(request, "Please upload a cover image.")
        return redirect('studio_home')

    # Create project record
    project = VideoProject.objects.create(
        title=title,
        audio_file=audio_file,
        cover_image=cover_image,
        video_format=video_format,
        render_status=VideoProject.Status.RENDERING
    )

    studio_videos_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'videos')
    os.makedirs(studio_videos_dir, exist_ok=True)

    try:
        artwork_path = project.cover_image.path
        audio_path = project.audio_file.path

        if video_format == VideoProject.VideoFormat.ONE_HOUR_LOOP:
            out_filename = f"studio_{project.id}_1hour_loop.mp4"
            out_path = os.path.join(studio_videos_dir, out_filename)
            VideoStudioRenderer.render_1hour_loop(artwork_path, audio_path, out_path, duration_seconds=3600)
            project.duration_seconds = 3600
            success_msg = f"Generated 1-Hour Study Loop for '{project.title}'!"

        elif video_format == VideoProject.VideoFormat.SHORT:
            out_filename = f"studio_{project.id}_short.mp4"
            out_path = os.path.join(studio_videos_dir, out_filename)
            VideoStudioRenderer.render_short(artwork_path, audio_path, out_path, start_seconds=30, duration_seconds=15)
            project.duration_seconds = 15
            success_msg = f"Generated 15s YouTube Shorts vertical hook for '{project.title}'!"

        else:  # VISUALIZER
            out_filename = f"studio_{project.id}_visualizer.mp4"
            out_path = os.path.join(studio_videos_dir, out_filename)
            VideoStudioRenderer.render_visualizer(artwork_path, audio_path, out_path)
            project.duration_seconds = 180
            success_msg = f"Generated 1080p Official Visualizer for '{project.title}'!"

        # Save output video file
        with open(out_path, 'rb') as f:
            project.output_video.save(out_filename, File(f), save=False)

        project.render_status = VideoProject.Status.COMPLETED
        project.save()
        messages.success(request, success_msg)

    except Exception as e:
        project.render_status = VideoProject.Status.FAILED
        project.error_message = str(e)
        project.save()
        messages.error(request, f"Video generation notice: {str(e)}")

    return redirect('studio_home')


@login_required
@require_POST
def studio_delete_view(request, pk):
    """
    Deletes a generated single loop video project.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    project = get_object_or_404(VideoProject, pk=pk)
    title = project.title
    project.delete()
    messages.info(request, f"Deleted video project '{title}'.")
    return redirect('studio_home')


# =========================================================================
# NON-STOP CONTINUOUS LONG MIX MAKER VIEWS
# =========================================================================

@login_required
def mix_maker_view(request):
    """
    Interactive Continuous Long Mix Builder.
    Allows uploading multiple songs, importing from catalog / YouTube, configuring crossfade, and cover art.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    catalog_videos = Video.objects.filter(is_active=True).select_related('artist', 'channel').order_by('-current_views')[:30]

    return render(request, 'studio/mix_maker.html', {
        'catalog_videos': catalog_videos,
        'transition_choices': LongMixProject.TransitionCurve.choices,
    })


@login_required
@require_POST
def mix_render_view(request):
    """
    Processes multiple audio tracks, calculates timeline, blends via FFmpeg acrossfade,
    and optionally renders 1080p MP4 long mix video.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    title = request.POST.get('title', '').strip() or 'My Non-Stop Music Mix'
    description = request.POST.get('description', '').strip()
    crossfade_seconds = int(request.POST.get('crossfade_seconds', 6))
    transition_curve = request.POST.get('transition_curve', LongMixProject.TransitionCurve.QSIN)
    render_video = request.POST.get('render_video') in ['true', '1', 'on']
    cover_image = request.FILES.get('cover_image')

    uploaded_files = request.FILES.getlist('track_files')
    track_titles = request.POST.getlist('track_titles[]')
    track_artists = request.POST.getlist('track_artists[]')
    track_urls = request.POST.getlist('track_urls[]')

    if not uploaded_files and not any(track_urls):
        messages.error(request, "Please add at least 2 audio tracks to create a continuous mix.")
        return redirect('mix_maker')

    # Create project entry
    project = LongMixProject.objects.create(
        title=title,
        description=description,
        cover_image=cover_image,
        transition_curve=transition_curve,
        crossfade_seconds=crossfade_seconds,
        render_video=render_video,
        render_status=LongMixProject.Status.RENDERING
    )

    project_source_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'mix_source', str(project.id))
    os.makedirs(project_source_dir, exist_ok=True)
    mix_output_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'mixes')
    os.makedirs(mix_output_dir, exist_ok=True)

    try:
        collected_tracks = []
        track_idx = 0

        # Process uploaded audio files
        for f in uploaded_files:
            dest_path = os.path.join(project_source_dir, f"track_{track_idx + 1}_{f.name}")
            with open(dest_path, 'wb+') as destination:
                for chunk in f.chunks():
                    destination.write(chunk)

            # Extract title and artist from post lists if provided
            t_title = track_titles[track_idx] if track_idx < len(track_titles) and track_titles[track_idx] else os.path.splitext(f.name)[0]
            t_artist = track_artists[track_idx] if track_idx < len(track_artists) else ''

            dur = MixEngineService.inspect_audio_duration(dest_path)
            collected_tracks.append({
                'title': t_title,
                'artist': t_artist,
                'duration': dur,
                'path': dest_path,
            })
            track_idx += 1

        # Process any imported YouTube URLs / Catalog items
        for url in track_urls:
            if url and url.strip():
                try:
                    dest_path, downloaded_title, dur = MixEngineService.download_youtube_audio(url.strip(), project_source_dir)
                    t_title = track_titles[track_idx] if track_idx < len(track_titles) and track_titles[track_idx] else downloaded_title
                    t_artist = track_artists[track_idx] if track_idx < len(track_artists) else ''
                    collected_tracks.append({
                        'title': t_title,
                        'artist': t_artist,
                        'duration': dur,
                        'path': dest_path,
                    })
                    track_idx += 1
                except Exception as dl_err:
                    # Continue with other tracks if one download fails
                    pass

        if not collected_tracks:
            raise ValueError("No valid audio tracks could be processed for mixing.")

        # 1. Calculate timeline and exact start timestamps
        timeline, total_duration = MixEngineService.calculate_track_timeline(
            collected_tracks,
            crossfade_seconds=crossfade_seconds
        )

        # 2. Render continuous master audio
        audio_paths = [t['path'] for t in timeline]
        out_audio_filename = f"mix_{project.id}_master.mp3"
        out_audio_path = os.path.join(mix_output_dir, out_audio_filename)

        MixEngineService.render_continuous_mix(
            audio_paths=audio_paths,
            output_mp3_path=out_audio_path,
            crossfade_seconds=crossfade_seconds,
            transition_curve=transition_curve
        )

        with open(out_audio_path, 'rb') as f:
            project.output_audio.save(out_audio_filename, File(f), save=False)

        # 3. Optionally render 1080p MP4 video
        if render_video:
            artwork_path = project.cover_image.path if project.cover_image else None
            out_video_filename = f"mix_{project.id}_1080p.mp4"
            out_video_path = os.path.join(mix_output_dir, out_video_filename)

            MixEngineService.render_mix_video(
                artwork_path=artwork_path,
                audio_path=out_audio_path,
                output_mp4_path=out_video_path,
                title=project.title
            )

            with open(out_video_path, 'rb') as f:
                project.output_video.save(out_video_filename, File(f), save=False)

        # 4. Save metadata
        project.track_count = len(timeline)
        project.duration_seconds = int(total_duration)
        project.tracklist_data = timeline
        project.render_status = LongMixProject.Status.COMPLETED
        project.save()

        messages.success(request, f"Successfully created nonstop mix '{project.title}' with {project.track_count} tracks ({project.duration_formatted})!")
        return redirect('mix_detail', pk=project.id)

    except Exception as e:
        project.render_status = LongMixProject.Status.FAILED
        project.error_message = str(e)
        project.save()
        messages.error(request, f"Mix rendering notice: {str(e)}")
        return redirect('mix_detail', pk=project.id)


@login_required
def mix_detail_view(request, pk):
    """
    Displays the created continuous mix project:
    - Continuous audio player with chapter seeking
    - Full tracklist with exact start timestamps
    - 1-Click Copy YouTube Chapters / Description
    - Direct MP3 & MP4 Downloads
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    project = get_object_or_404(LongMixProject, pk=pk)
    
    return render(request, 'studio/mix_detail.html', {
        'project': project,
    })


@login_required
@require_POST
def mix_delete_view(request, pk):
    """
    Deletes a continuous mix project and its generated media.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    project = get_object_or_404(LongMixProject, pk=pk)
    title = project.title
    project.delete()
    messages.info(request, f"Deleted nonstop mix project '{title}'.")
    return redirect('studio_home')


@login_required
def mix_import_api(request):
    """
    AJAX helper to lookup catalog videos by query.
    """
    if not request.user.is_super_admin:
        return JsonResponse({'error': 'Super Admin privileges required.'}, status=403)

    query = request.GET.get('q', '').strip()
    videos = Video.objects.filter(is_active=True)
    if query:
        videos = videos.filter(title__icontains=query) | videos.filter(artist__stage_name__icontains=query)

    results = []
    for v in videos[:15]:
        results.append({
            'id': v.id,
            'title': v.title,
            'artist': v.artist.stage_name if v.artist else '',
            'duration': v.duration or '03:30',
            'thumbnail': v.thumbnail_url or '',
            'url': v.video_url or '',
        })

    return JsonResponse({'results': results})

