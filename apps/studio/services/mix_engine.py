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
        except Exception as e:
            pass

        return 180.0  # Safe fallback 3 minutes

    @classmethod
    def calculate_track_timeline(cls, track_items, crossfade_seconds=6):
        """
        Calculates exact start and end timestamps for each track in the blended mix.
        Formula:
        Track 0: start = 0.0, end = dur_0
        Track k: start = track_{k-1}.end - crossfade, end = start + dur_k
        """
        timeline = []
        current_time = 0.0
        crossfade = max(1.0, float(crossfade_seconds))

        for idx, item in enumerate(track_items):
            title = item.get('title', f"Track {idx + 1}")
            artist = item.get('artist', '')
            duration = float(item.get('duration', 180.0))
            if duration <= 0:
                duration = 180.0

            if idx == 0:
                start_sec = 0.0
            else:
                start_sec = max(0.0, current_time - crossfade)

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
                'source_path': item.get('path', ''),
            })

        total_mix_duration = round(current_time, 1) if timeline else 0.0
        return timeline, total_mix_duration

    @classmethod
    def render_continuous_mix(cls, audio_paths, output_mp3_path, crossfade_seconds=6, transition_curve='qsin'):
        """
        Takes an ordered list of audio file paths and blends them into a single seamless continuous MP3.
        Uses FFmpeg 'acrossfade' audio filter with sample rate & channel unification.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp3_path = os.path.abspath(str(output_mp3_path))
        os.makedirs(os.path.dirname(output_mp3_path), exist_ok=True)

        if not audio_paths:
            raise ValueError("No audio tracks provided for mixing.")

        if len(audio_paths) == 1:
            # Single track: simple transcode to MP3
            cmd = [
                ffmpeg, '-y',
                '-i', os.path.abspath(str(audio_paths[0])),
                '-c:a', 'libmp3lame',
                '-b:a', '192k',
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
        xfade_dur = 1.5 if str(transition_curve).lower() == 'fast' else max(1.0, float(crossfade_seconds))

        # Build FFmpeg command with filter complex
        # Step A: Normalize all inputs to 44.1kHz Stereo
        # Step B: Chain acrossfade filters
        input_args = []
        filter_parts = []

        for i, path in enumerate(audio_paths):
            input_args.extend(['-i', os.path.abspath(str(path))])
            filter_parts.append(f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a_in_{i}]")

        # Now chain the normalized audio streams:
        num_tracks = len(audio_paths)
        prev_label = "[a_in_0]"

        for i in range(1, num_tracks):
            next_input = f"[a_in_{i}]"
            out_label = "[aout]" if i == num_tracks - 1 else f"[mix_{i}]"
            filter_parts.append(
                f"{prev_label}{next_input}acrossfade=d={xfade_dur}:c1={c1}:c2={c2}{out_label}"
            )
            prev_label = out_label

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
        Darkened blurred backdrop with centered crisp artwork.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp4_path = os.path.abspath(str(output_mp4_path))
        audio_path = os.path.abspath(str(audio_path))
        os.makedirs(os.path.dirname(output_mp4_path), exist_ok=True)

        temp_bg = output_mp4_path.replace('.mp4', '_mix_bg.jpg')

        try:
            if artwork_path and os.path.exists(str(artwork_path)):
                VideoStudioRenderer.prepare_16_9_background(str(artwork_path), temp_bg)
            else:
                # Generate a sleek dark gradient backdrop if no artwork provided
                img = Image.new('RGB', (1920, 1080), color=(15, 15, 20))
                draw = ImageDraw.Draw(img)
                # Draw subtle decorative ambient rectangles
                draw.rectangle([(200, 200), (1720, 880)], outline=(35, 35, 45), width=2)
                img.save(temp_bg, format='JPEG', quality=90)

            cmd = [
                ffmpeg, '-y',
                '-loop', '1',
                '-i', temp_bg,
                '-i', audio_path,
                '-c:v', 'libx264',
                '-tune', 'stillimage',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-pix_fmt', 'yuv420p',
                '-shortest',
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
