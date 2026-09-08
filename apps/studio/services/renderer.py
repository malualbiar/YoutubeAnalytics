import os
import sys
import shutil
import glob
import subprocess
import math
from PIL import Image, ImageFilter, ImageEnhance

from django.conf import settings

class VideoStudioRenderer:

    @classmethod
    def get_ffmpeg_binary(cls):
        # 1. Check local project bin/ffmpeg.exe
        local_bin = os.path.join(settings.BASE_DIR, 'bin', 'ffmpeg.exe')
        if os.path.exists(local_bin):
            return local_bin

        # 2. Try imageio_ffmpeg module
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                return exe
        except Exception:
            pass

        # 3. Check system PATH
        system_ffmpeg = shutil.which('ffmpeg')
        if system_ffmpeg:
            return system_ffmpeg

        # 4. Search site-packages directories for imageio_ffmpeg binaries
        try:
            for p in sys.path:
                pattern = os.path.join(p, 'imageio_ffmpeg', 'binaries', 'ffmpeg*')
                matches = glob.glob(pattern)
                for match in matches:
                    if os.path.exists(match) and match.endswith('.exe'):
                        return match
        except Exception:
            pass

        raise FileNotFoundError(
            "FFmpeg executable not found. Please restart your server so Python picks up imageio-ffmpeg."
        )

    @classmethod
    def get_subprocess_kwargs(cls):
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        return kwargs

    @classmethod
    def get_optimal_encoder_args(cls, is_still_image=False, crf=20):
        """
        Returns high-speed optimal video encoder arguments with multi-threading.
        Uses libx264 with -preset veryfast and -threads 0 for maximum multi-core CPU throughput.
        """
        args = [
            '-c:v', 'libx264',
            '-preset', 'veryfast',
            '-crf', str(crf),
            '-threads', '0',
            '-pix_fmt', 'yuv420p',
        ]
        if is_still_image:
            args.extend(['-tune', 'stillimage'])
        return args

    @classmethod
    def prepare_16_9_background(cls, artwork_path, output_bg_path):
        """
        Creates a crisp 1920x1080 16:9 canvas with blurred background and centered cover art.
        """
        img = Image.open(artwork_path).convert('RGB')
        
        # 1. Blurred darkened 16:9 background
        bg = img.resize((1920, 1080), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=25))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.4)

        # 2. Centered crisp artwork (960x960 square)
        center_art = img.resize((960, 960), Image.Resampling.LANCZOS)
        bg.paste(center_art, (480, 60))
        bg.save(output_bg_path, format='JPEG', quality=95)
        return output_bg_path

    @classmethod
    def prepare_9_16_background(cls, artwork_path, output_bg_path):
        """
        Creates a vertical 1080x1920 9:16 canvas for YouTube Shorts & TikTok.
        """
        img = Image.open(artwork_path).convert('RGB')
        
        bg = img.resize((1080, 1920), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.35)

        center_art = img.resize((960, 960), Image.Resampling.LANCZOS)
        bg.paste(center_art, (60, 480))
        bg.save(output_bg_path, format='JPEG', quality=95)
        return output_bg_path

    @classmethod
    def render_1hour_loop(cls, artwork_path, audio_path, output_mp4_path, duration_seconds=3600):
        """
        Renders a 1-Hour extended loop video for YouTube watch-time.
        Uses stream loop for fast rendering.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp4_path = os.path.abspath(str(output_mp4_path))
        artwork_path = os.path.abspath(str(artwork_path))
        audio_path = os.path.abspath(str(audio_path))
        temp_bg = output_mp4_path.replace('.mp4', '_loop_bg.jpg')

        try:
            cls.prepare_16_9_background(artwork_path, temp_bg)

            cmd = [
                ffmpeg,
                '-y',
                '-loop', '1',
                '-i', temp_bg,
                '-stream_loop', '-1',
                '-i', audio_path,
                '-t', str(duration_seconds),
                *cls.get_optimal_encoder_args(is_still_image=True),
                '-c:a', 'aac',
                '-b:a', '192k',
                output_mp4_path
            ]

            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **cls.get_subprocess_kwargs())
            return output_mp4_path
        finally:
            if os.path.exists(temp_bg):
                try:
                    os.remove(temp_bg)
                except Exception:
                    pass

    @classmethod
    def render_visualizer(cls, artwork_path, audio_path, output_mp4_path):
        """
        Renders a 1080p 16:9 visualizer matching the exact track duration.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp4_path = os.path.abspath(str(output_mp4_path))
        artwork_path = os.path.abspath(str(artwork_path))
        audio_path = os.path.abspath(str(audio_path))
        temp_bg = output_mp4_path.replace('.mp4', '_vis_bg.jpg')

        try:
            cls.prepare_16_9_background(artwork_path, temp_bg)

            cmd = [
                ffmpeg,
                '-y',
                '-loop', '1',
                '-i', temp_bg,
                '-i', audio_path,
                *cls.get_optimal_encoder_args(is_still_image=True),
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                output_mp4_path
            ]

            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **cls.get_subprocess_kwargs())
            return output_mp4_path
        finally:
            if os.path.exists(temp_bg):
                try:
                    os.remove(temp_bg)
                except Exception:
                    pass

    @classmethod
    def render_short(cls, artwork_path, audio_path, output_mp4_path, start_seconds=30, duration_seconds=15):
        """
        Renders a 15-second vertical (9:16) video snippet for YouTube Shorts.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_mp4_path = os.path.abspath(str(output_mp4_path))
        artwork_path = os.path.abspath(str(artwork_path))
        audio_path = os.path.abspath(str(audio_path))
        temp_bg = output_mp4_path.replace('.mp4', '_short_bg.jpg')

        try:
            cls.prepare_9_16_background(artwork_path, temp_bg)

            cmd = [
                ffmpeg,
                '-y',
                '-loop', '1',
                '-i', temp_bg,
                '-ss', str(start_seconds),
                '-t', str(duration_seconds),
                '-i', audio_path,
                *cls.get_optimal_encoder_args(is_still_image=True),
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                output_mp4_path
            ]

            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **cls.get_subprocess_kwargs())
            return output_mp4_path
        finally:
            if os.path.exists(temp_bg):
                try:
                    os.remove(temp_bg)
                except Exception:
                    pass
