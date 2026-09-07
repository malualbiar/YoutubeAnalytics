import os
import shutil
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
import json
import zipfile
from io import BytesIO
from django.core.files import File
from django.http import HttpResponse, JsonResponse
from .models import VideoProject, LongMixProject, ShortVideoProject
from .services.renderer import VideoStudioRenderer
from .services.mix_engine import MixEngineService
from .services.shorts_engine import ShortsEngineService
from apps.videos.models import Video

@login_required
def studio_home_view(request):
    """
    Main YouTube Video Studio dashboard: displays 1-Hour Loops, Non-Stop Mixes, and Short Clips.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    tab = request.GET.get('tab', 'shorts')
    single_loops = VideoProject.objects.all().order_by('-created_at')
    mix_projects = LongMixProject.objects.all().order_by('-created_at')
    short_projects = ShortVideoProject.objects.all().order_by('-created_at')
    
    total_mix_duration = sum(m.duration_seconds for m in mix_projects)
    total_loop_duration = sum(p.duration_seconds for p in single_loops)
    total_shorts_duration = sum(s.duration_seconds for s in short_projects)
    total_hours_produced = round((total_mix_duration + total_loop_duration + total_shorts_duration) / 3600, 1)

    total_shorts_count = sum(s.chop_count for s in short_projects)

    return render(request, 'studio/index.html', {
        'tab': tab,
        'projects': single_loops,
        'mix_projects': mix_projects,
        'short_projects': short_projects,
        'total_shorts_count': total_shorts_count,
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


# =========================================================================
# SHORT VIDEO GENERATOR & MULTI-CLIP VIDEO CHOPPER VIEWS
# =========================================================================

@login_required
def shorts_maker_view(request):
    """
    Interactive Short Video Generator & Multi-Clip Chopper UI:
    - Upload long video or audio+cover track
    - Interactive visual timeline with draggable / movable chops
    - 1-Click Auto-Split tools (15s, 30s, 60s)
    - Live Preview Player seeking only chop boundaries
    - Real-time 9:16 vertical phone mockup preview
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    catalog_videos = Video.objects.filter(is_active=True).select_related('artist', 'channel').order_by('-current_views')[:30]

    return render(request, 'studio/shorts_maker.html', {
        'catalog_videos': catalog_videos,
        'source_choices': ShortVideoProject.SourceType.choices,
        'aspect_choices': ShortVideoProject.AspectMode.choices,
        'theme_choices': ShortVideoProject.ThemeStyle.choices,
    })


@login_required
@require_POST
def shorts_render_view(request):
    """
    Processes the uploaded long video or audio+cover, applies chop cuts, renders 1080x1920 (9:16)
    vertical clips with blurred backgrounds and hook overlays, and stores output files.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    title = request.POST.get('title', '').strip() or 'My Viral Shorts & Reels'
    source_type = request.POST.get('source_type', ShortVideoProject.SourceType.VIDEO)
    aspect_mode = request.POST.get('aspect_mode', ShortVideoProject.AspectMode.BLURRED_FIT)
    theme_style = request.POST.get('theme_style', ShortVideoProject.ThemeStyle.VIRAL_HOOK)

    source_video = request.FILES.get('source_video')
    audio_file = request.FILES.get('audio_file')
    cover_image = request.FILES.get('cover_image')
    chops_json = request.POST.get('chops_json', '').strip()

    if source_type == ShortVideoProject.SourceType.VIDEO and not source_video:
        messages.error(request, "Please upload a video file (.mp4, .mov, .mkv).")
        return redirect('shorts_maker')

    if source_type == ShortVideoProject.SourceType.AUDIO_COVER and (not audio_file or not cover_image):
        messages.error(request, "Please upload both an audio file and a cover image.")
        return redirect('shorts_maker')

    # Create project record
    project = ShortVideoProject.objects.create(
        title=title,
        source_type=source_type,
        source_video=source_video,
        audio_file=audio_file,
        cover_image=cover_image,
        aspect_mode=aspect_mode,
        theme_style=theme_style,
        render_status=ShortVideoProject.Status.RENDERING
    )

    project_output_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'shorts_output', str(project.id))
    os.makedirs(project_output_dir, exist_ok=True)

    try:
        # Determine source duration
        if source_type == ShortVideoProject.SourceType.VIDEO:
            src_path = project.source_video.path
            total_duration = ShortsEngineService.inspect_media_duration(src_path)
        else:
            src_path = project.audio_file.path
            total_duration = ShortsEngineService.inspect_media_duration(src_path)

        project.duration_seconds = total_duration

        # Parse or generate chops
        chops = []
        if chops_json:
            try:
                parsed = json.loads(chops_json)
                if isinstance(parsed, list) and len(parsed) > 0:
                    chops = parsed
            except Exception:
                pass

        if not chops:
            chops = ShortsEngineService.generate_chop_splits(total_duration, interval_seconds=15.0)

        rendered_chops = []
        first_output_path = None

        for idx, chop in enumerate(chops):
            chop_id = idx + 1
            chop_title = chop.get('title', f"Part {chop_id}")
            hook_text = chop.get('hook_text', '')
            start_s = float(chop.get('start_seconds', 0.0))
            end_s = float(chop.get('end_seconds', start_s + 15.0))
            dur_s = max(1.0, round(end_s - start_s, 2))

            out_filename = f"short_{project.id}_part{chop_id}.mp4"
            out_path = os.path.join(project_output_dir, out_filename)
            overlay_png = os.path.join(project_output_dir, f"overlay_part{chop_id}.png")

            # Generate overlay if needed
            if theme_style != ShortVideoProject.ThemeStyle.CLEAN or hook_text:
                ShortsEngineService.prepare_overlay_banner(
                    hook_text=hook_text,
                    part_label=f"Part {chop_id}",
                    theme=theme_style,
                    width=1080,
                    height=1920,
                    output_png_path=overlay_png
                )
            else:
                overlay_png = None

            # Render chop
            if source_type == ShortVideoProject.SourceType.VIDEO:
                ShortsEngineService.render_video_chop(
                    source_video_path=src_path,
                    output_mp4_path=out_path,
                    start_seconds=start_s,
                    duration_seconds=dur_s,
                    aspect_mode=aspect_mode,
                    overlay_png_path=overlay_png
                )
            else:
                ShortsEngineService.render_audio_cover_chop(
                    cover_path=project.cover_image.path,
                    audio_path=src_path,
                    output_mp4_path=out_path,
                    start_seconds=start_s,
                    duration_seconds=dur_s,
                    overlay_png_path=overlay_png
                )

            # Cleanup overlay PNG
            if overlay_png and os.path.exists(overlay_png):
                try:
                    os.remove(overlay_png)
                except Exception:
                    pass

            rel_url = f"{settings.MEDIA_URL}studio/shorts_output/{project.id}/{out_filename}"
            rendered_chops.append({
                'id': chop_id,
                'title': chop_title,
                'hook_text': hook_text,
                'start_seconds': start_s,
                'end_seconds': end_s,
                'duration': dur_s,
                'output_file': out_filename,
                'output_url': rel_url,
                'status': 'COMPLETED'
            })

            if idx == 0:
                first_output_path = out_path

        # Link first rendered chop to project.output_video
        if first_output_path and os.path.exists(first_output_path):
            with open(first_output_path, 'rb') as f:
                project.output_video.save(os.path.basename(first_output_path), f, save=False)

        project.chops_data = rendered_chops
        project.chop_count = len(rendered_chops)
        project.render_status = ShortVideoProject.Status.COMPLETED
        project.save()

        messages.success(request, f"Successfully created {project.chop_count} vertical 9:16 shorts for '{project.title}'!")
        return redirect('shorts_detail', pk=project.id)

    except Exception as e:
        project.render_status = ShortVideoProject.Status.FAILED
        project.error_message = str(e)
        project.save()
        messages.error(request, f"Shorts generation error: {str(e)}")
        return redirect('shorts_detail', pk=project.id)


@login_required
def shorts_detail_view(request, pk):
    """
    Detail page for a Shorts & Reels project:
    - Visual gallery of 9:16 vertical clips
    - Built-in vertical player with part selection
    - 1-Click Copy Title, SEO Description & Tags for each chop
    - Individual and All-in-One Download buttons
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    project = get_object_or_404(ShortVideoProject, pk=pk)
    
    # Prepare enriched chop items with copyable titles and descriptions
    enriched_chops = []
    for idx, c in enumerate(project.chops_data or []):
        c_copy = dict(c)
        c_copy['youtube_title'] = project.youtube_title_for_chop(idx)
        c_copy['youtube_description'] = project.youtube_description_for_chop(idx)
        enriched_chops.append(c_copy)

    return render(request, 'studio/short_detail.html', {
        'project': project,
        'chops': enriched_chops,
    })


@login_required
@require_POST
def shorts_delete_view(request, pk):
    """
    Deletes a short video project and cleans up its media files.
    """
    if not request.user.is_super_admin:
        messages.error(request, "Access denied. Super Admin privileges required.")
        return redirect('dashboard')

    project = get_object_or_404(ShortVideoProject, pk=pk)
    title = project.title
    
    # Cleanup output folder
    project_output_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'shorts_output', str(project.id))
    if os.path.exists(project_output_dir):
        try:
            shutil.rmtree(project_output_dir)
        except Exception:
            pass

    project.delete()
    messages.info(request, f"Deleted shorts project '{title}'.")
    return redirect('studio_home')


@login_required
def shorts_export_zip_view(request, pk):
    """
    Downloads all rendered vertical chops in a single ZIP archive.
    """
    if not request.user.is_super_admin:
        return HttpResponse("Access denied", status=403)

    project = get_object_or_404(ShortVideoProject, pk=pk)
    project_output_dir = os.path.join(settings.MEDIA_ROOT, 'studio', 'shorts_output', str(project.id))

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for chop in project.chops_data or []:
            fn = chop.get('output_file')
            if fn:
                full_path = os.path.join(project_output_dir, fn)
                if os.path.exists(full_path):
                    zip_file.write(full_path, arcname=fn)

    zip_buffer.seek(0)
    safe_title = "".join(c for c in project.title if c.isalnum() or c in (' ', '_', '-')).rstrip().replace(' ', '_')
    response = HttpResponse(zip_buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{safe_title}_Shorts_Package.zip"'
    return response


