import os
import sys
import shutil
import glob
import subprocess
import math
import re
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont

from django.conf import settings
from .renderer import VideoStudioRenderer

class MixEngineService:

    @classmethod
    def get_ffmpeg_binary(cls):
        return VideoStudioRenderer.get_ffmpeg_binary()

    @classmethod
    def inspect_audio_duration(cls, audio_path):
        """
        Inspects audio file and returns duration in seconds as float.
        Falls back to 180.0s if probe fails.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        audio_path = os.path.abspath(str(audio_path))
        
        try:
            cmd = [ffmpeg, '-i', audio_path]
            proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors='ignore')
            
            # Look for Duration: 00:03:45.67
            match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', proc.stderr)
            if match:
                hours = int(match.group(1))
                mins = int(match.group(2))
                secs = float(match.group(3))
                total_seconds = hours * 3600 + mins * 60 + secs
                return max(1.0, total_seconds)
        except Exception:
            pass

        return 180.0  # Safe fallback 3 minutes

    @classmethod
    def calculate_track_timeline(cls, track_items, crossfade_seconds=6):
        """
        Calculates exact start and end timestamps for each track in the blended mix.
        Formula:
        Track 0: start = 0.0, end = dur_0
        Track k: start = track_{k-1}.end - safe_crossfade, end = start + dur_k
        """
        timeline = []
        current_time = 0.0
        requested_crossfade = max(0.5, float(crossfade_seconds))

        for idx, item in enumerate(track_items):
            title = item.get('title', f"Track {idx + 1}")
            artist = item.get('artist', '')
            duration = float(item.get('duration', 180.0))
            if duration <= 0:
                duration = 180.0

            if idx == 0:
                start_sec = 0.0
            else:
                prev_dur = float(track_items[idx - 1].get('duration', 180.0))
                # Safe crossfade cannot exceed 45% of either track duration
                safe_crossfade = min(requested_crossfade, min(prev_dur, duration) * 0.45)
                safe_crossfade = max(0.2, safe_crossfade)
                start_sec = max(0.0, current_time - safe_crossfade)

            end_sec = start_sec + duration
            current_time = end_sec

            hours = int(start_sec) // 3600
            mins = (int(start_sec) % 3600) // 60
            secs = int(start_sec) % 60
            if hours > 0:
                time_str = f"{hours:02d}:{mins:02d}:{secs:02d}"
            else:
                time_str = f"{mins:02d}:{secs:02d}"

            timeline.append({
                'index': idx + 1,
                'title': title,
                'artist': artist,
                'duration': round(duration, 1),
                'start_seconds': round(start_sec, 2),
                'end_seconds': round(end_sec, 2),
                'start_time_str': time_str,
                'path': item.get('path', ''),
                'source_path': item.get('path', ''),
            })

        total_mix_duration = round(current_time, 1) if timeline else 0.0
        return timeline, total_mix_duration

    @classmethod
    def render_continuous_mix(cls, audio_paths, output_mp3_path, crossfade_seconds=6, transition_curve='qsin', normalize_volume=True):
        """
        Takes an ordered list of audio file paths and blends them into a single seamless continuous MP3.
        Uses FFmpeg 'acrossfade' audio filter with sample rate & channel unification and dynamic duration safety.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp3_path = os.path.abspath(str(output_mp3_path))
        os.makedirs(os.path.dirname(output_mp3_path), exist_ok=True)

        if not audio_paths:
            raise ValueError("No audio tracks provided for mixing.")

        # Inspect durations of each path to ensure acrossfade does not exceed track length
        durations = [cls.inspect_audio_duration(p) for p in audio_paths]

        if len(audio_paths) == 1:
            # Single track: simple transcode with volume normalization
            filters = ['aformat=sample_rates=44100:channel_layouts=stereo']
            if normalize_volume:
                filters.append('dynaudnorm=f=150:g=15')
            cmd = [
                ffmpeg, '-y',
                '-i', os.path.abspath(str(audio_paths[0])),
                '-af', ','.join(filters),
                '-c:a', 'libmp3lame',
                '-b:a', '256k',
                output_mp3_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output_mp3_path

        # Determine transition curve parameters
        curve_map = {
            'qsin': ('qsin', 'qsin'),
            'tri': ('tri', 'tri'),
            'lin': ('tri', 'tri'),
            'exp': ('exp', 'exp'),
            'fast': ('qsin', 'qsin'),
        }
        c1, c2 = curve_map.get(str(transition_curve).lower(), ('qsin', 'qsin'))
        base_xfade = 1.5 if str(transition_curve).lower() == 'fast' else max(0.5, float(crossfade_seconds))

        # Build FFmpeg command with filter complex
        # Step A: Normalize all inputs to 44.1kHz Stereo
        # Step B: Chain acrossfade filters with clamped safe fade duration
        input_args = []
        filter_parts = []

        for i, path in enumerate(audio_paths):
            input_args.extend(['-i', os.path.abspath(str(path))])
            filter_parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a_in_{i}]")

        # Now chain the normalized audio streams:
        num_tracks = len(audio_paths)
        prev_label = "[a_in_0]"

        for i in range(1, num_tracks):
            dur_prev = durations[i - 1]
            dur_curr = durations[i]
            # Safety clamp: acrossfade must be strictly less than half of either track duration
            safe_xfade = min(base_xfade, min(dur_prev, dur_curr) * 0.45)
            safe_xfade = max(0.2, round(safe_xfade, 2))

            next_input = f"[a_in_{i}]"
            out_label = "[mix_pre]" if (i == num_tracks - 1 and normalize_volume) else ("[aout]" if i == num_tracks - 1 else f"[mix_{i}]")
            filter_parts.append(
                f"{prev_label}{next_input}acrossfade=d={safe_xfade}:c1={c1}:c2={c2}{out_label}"
            )
            prev_label = out_label

        if normalize_volume:
            filter_parts.append("[mix_pre]dynaudnorm=f=150:g=15[aout]")

        filter_complex_str = ";".join(filter_parts)

        cmd = [
            ffmpeg, '-y',
            *input_args,
            '-filter_complex', filter_complex_str,
            '-map', '[aout]',
            '-c:a', 'libmp3lame',
            '-b:a', '256k',
            output_mp3_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='ignore')
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg mix rendering failed: {result.stderr[-400:]}")

        return output_mp3_path

    @classmethod
    def render_mix_video(cls, artwork_path, audio_path, output_mp4_path, title="Non-Stop Music Mix"):
        """
        Renders a 1080p 16:9 YouTube video canvas for the continuous mix.
        Darkened blurred backdrop with centered crisp artwork and explicit duration bounds.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp4_path = os.path.abspath(str(output_mp4_path))
        audio_path = os.path.abspath(str(audio_path))
        os.makedirs(os.path.dirname(output_mp4_path), exist_ok=True)

        audio_duration = cls.inspect_audio_duration(audio_path)
        temp_bg = output_mp4_path.replace('.mp4', '_mix_bg.jpg')

        try:
            if artwork_path and os.path.exists(str(artwork_path)):
                VideoStudioRenderer.prepare_16_9_background(str(artwork_path), temp_bg)
            else:
                # Generate a sleek dark solid backdrop if no artwork provided
                img = Image.new('RGB', (1920, 1080), color=(18, 18, 24))
                draw = ImageDraw.Draw(img)
                # Draw subtle crisp bounding box
                draw.rectangle([(160, 120), (1760, 960)], outline=(38, 38, 48), width=2)
                img.save(temp_bg, format='JPEG', quality=92)

            cmd = [
                ffmpeg, '-y',
                '-loop', '1',
                '-i', temp_bg,
                '-i', audio_path,
                '-t', str(round(audio_duration, 2)),
                '-c:v', 'libx264',
                '-tune', 'stillimage',
                '-pix_fmt', 'yuv420p',
                '-r', '1',
                '-c:a', 'aac',
                '-b:a', '192k',
                output_mp4_path
            ]

            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors='ignore')
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg video rendering failed: {result.stderr[-400:]}")

            return output_mp4_path
        finally:
            if os.path.exists(temp_bg):
                try:
                    os.remove(temp_bg)
                except Exception:
                    pass

    @classmethod
    def download_youtube_audio(cls, url_or_video_id, target_dir):
        """
        Downloads audio from YouTube video via yt-dlp into target directory.
        Returns (audio_filepath, title, duration).
        """
        import yt_dlp
        os.makedirs(target_dir, exist_ok=True)

        if not url_or_video_id.startswith('http'):
            url = f"https://www.youtube.com/watch?v={url_or_video_id}"
        else:
            url = url_or_video_id

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(target_dir, '%(id)s_%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'YouTube Track')
            duration = float(info.get('duration', 180.0))
            video_id = info.get('id', 'track')
            
            # Find output mp3 file
            pattern = os.path.join(target_dir, f"{video_id}_*.mp3")
            matches = glob.glob(pattern)
            if matches:
                return matches[0], title, duration

            # Fallback search
            for f in os.listdir(target_dir):
                if f.startswith(video_id) and f.endswith('.mp3'):
                    return os.path.join(target_dir, f), title, duration

        raise FileNotFoundError(f"Could not extract audio for URL: {url}")
