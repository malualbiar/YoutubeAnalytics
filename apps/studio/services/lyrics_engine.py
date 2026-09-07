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

class LyricsEngineService:

    @classmethod
    def get_ffmpeg_binary(cls):
        return VideoStudioRenderer.get_ffmpeg_binary()

    @classmethod
    def inspect_media_duration(cls, file_path):
        """
        Inspects video or audio file and returns duration in seconds as float.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        file_path = os.path.abspath(str(file_path))
        
        try:
            cmd = [ffmpeg, '-i', file_path]
            proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, errors='ignore')
            match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', proc.stderr)
            if match:
                hours = int(match.group(1))
                mins = int(match.group(2))
                secs = float(match.group(3))
                total_seconds = hours * 3600 + mins * 60 + secs
                return max(1.0, round(total_seconds, 2))
        except Exception:
            pass

        return 60.0

    @classmethod
    def parse_lrc_file(cls, lrc_text):
        """
        Parses standard .LRC synchronized lyrics text format:
        [00:12.34]Lyric line text
        Returns a sorted list of dicts:
        [{'line': '...', 'start': 12.34, 'end': 16.50}, ...]
        """
        if not lrc_text:
            return []

        lines = lrc_text.strip().splitlines()
        parsed_entries = []

        # Matches [mm:ss.xx] or [mm:ss:xx] or [mm:ss]
        pattern = re.compile(r'\[(\d{1,2}):(\d{2})(?:[\.:](\d{1,3}))?\]')

        for raw_line in lines:
            raw_line = raw_line.strip()
            if not raw_line or raw_line.startswith('[ti:') or raw_line.startswith('[ar:') or raw_line.startswith('[al:') or raw_line.startswith('[by:'):
                continue

            matches = list(pattern.finditer(raw_line))
            if not matches:
                continue

            # Strip all timestamps from the line to get the lyric text
            lyric_text = pattern.sub('', raw_line).strip()

            for match in matches:
                mins = int(match.group(1))
                secs = int(match.group(2))
                ms_raw = match.group(3)
                
                if ms_raw:
                    if len(ms_raw) == 2:
                        frac = int(ms_raw) / 100.0
                    else:
                        frac = int(ms_raw) / 1000.0
                else:
                    frac = 0.0

                timestamp = round(mins * 60 + secs + frac, 2)
                parsed_entries.append({
                    'start': timestamp,
                    'line': lyric_text
                })

        # Sort chronologically by start timestamp
        parsed_entries.sort(key=lambda x: x['start'])

        # Compute end timestamp for each line
        result = []
        for i, entry in enumerate(parsed_entries):
            start = entry['start']
            line = entry['line']
            if not line:
                continue

            if i + 1 < len(parsed_entries):
                next_start = parsed_entries[i + 1]['start']
                end = min(next_start, round(start + 8.0, 2))
                if end <= start:
                    end = round(start + 3.0, 2)
            else:
                end = round(start + 5.0, 2)

            result.append({
                'line': line,
                'start': start,
                'end': end
            })

        return result

    @classmethod
    def export_lrc_string(cls, lyrics_data, title='', artist=''):
        """
        Exports lyrics_data list to standard .LRC format string.
        """
        lines = []
        if title:
            lines.append(f"[ti:{title}]")
        if artist:
            lines.append(f"[ar:{artist}]")
        lines.append("[by:YT Quid Creator Studio]")

        for item in lyrics_data:
            start_sec = float(item.get('start', 0.0))
            mins = int(start_sec // 60)
            secs = int(start_sec % 60)
            centis = int(round((start_sec - int(start_sec)) * 100))
            lyric = item.get('line', '').strip()
            if lyric:
                lines.append(f"[{mins:02d}:{secs:02d}.{centis:02d}]{lyric}")

        return "\n".join(lines)

    @classmethod
    def auto_distribute_raw_lyrics(cls, raw_text, total_duration):
        """
        Evenly distributes raw un-synced text lines across the total audio duration.
        """
        raw_lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
        if not raw_lines:
            return []

        count = len(raw_lines)
        total = max(5.0, float(total_duration))
        # Add 2s lead-in padding and 2s outro padding
        lead_in = 2.0
        active_duration = max(2.0, total - lead_in - 2.0)
        slot_duration = active_duration / count

        result = []
        for idx, line in enumerate(raw_lines):
            start = round(lead_in + (idx * slot_duration), 2)
            end = round(min(total, start + slot_duration * 0.92), 2)
            result.append({
                'line': line,
                'start': start,
                'end': end
            })

        return result

    @classmethod
    def detect_vocal_segments(cls, audio_path, min_silence_duration=0.35, noise_threshold_db=-30):
        """
        Uses vocal frequency bandpass filtering (300Hz-3400Hz) and silence detection
        to identify active vocal singing segments vs instrumental intros, solos & breaks.
        Returns list of dicts:
        [{'start': 12.4, 'end': 16.8, 'duration': 4.4}, ...]
        """
        ffmpeg = cls.get_ffmpeg_binary()
        audio_path = os.path.abspath(str(audio_path))
        total_duration = cls.inspect_media_duration(audio_path)

        # 1. Bandpass filter around vocal formant region (300Hz to 3800Hz)
        # 2. Dynamic gate / compand to isolate singing energy
        # 3. Silence detector
        af_filter = (
            f"bandpass=f=1850:width_type=h:w=3100,"
            f"compand=attacks=0.03:decays=0.15:points=-80/-80|-45/-30|-20/-10|0/0,"
            f"silencedetect=noise={noise_threshold_db}dB:d={min_silence_duration}"
        )

        cmd = [
            ffmpeg, '-i', audio_path,
            '-af', af_filter,
            '-f', 'null', '-'
        ]

        try:
            proc = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                errors='ignore'
            )

            silence_ranges = []
            cur_silence_start = None

            for line in proc.stderr.splitlines():
                if 'silence_start:' in line:
                    m = re.search(r'silence_start:\s*([0-9.]+)', line)
                    if m:
                        cur_silence_start = float(m.group(1))
                elif 'silence_end:' in line:
                    m = re.search(r'silence_end:\s*([0-9.]+)', line)
                    if m:
                        end_t = float(m.group(1))
                        start_t = cur_silence_start if cur_silence_start is not None else 0.0
                        silence_ranges.append((start_t, end_t))
                        cur_silence_start = None

            vocal_segments = []
            last_end = 0.0

            for s_start, s_end in silence_ranges:
                if s_start > last_end + 0.5:
                    vocal_segments.append({
                        'start': round(last_end, 2),
                        'end': round(s_start, 2),
                        'duration': round(s_start - last_end, 2)
                    })
                last_end = s_end

            if total_duration > last_end + 0.5:
                vocal_segments.append({
                    'start': round(last_end, 2),
                    'end': round(total_duration, 2),
                    'duration': round(total_duration - last_end, 2)
                })

            valid_segments = [s for s in vocal_segments if s['duration'] >= 0.6]
            return valid_segments if valid_segments else [{'start': 2.0, 'end': total_duration - 1.0, 'duration': total_duration - 3.0}]

        except Exception:
            return [{'start': 2.0, 'end': total_duration - 1.0, 'duration': total_duration - 3.0}]

    @classmethod
    def align_lyrics_with_vocal_segments(cls, raw_text, vocal_segments, total_duration):
        """
        Maps raw lyrics lines to detected vocal frequency segments, ensuring
        no lyrics are displayed during instrumental solos, intros, and drum breaks.
        """
        lines = [l.strip() for l in raw_text.strip().splitlines() if l.strip()]
        cleaned_lines = [l for l in lines if not (l.startswith('[') and l.endswith(']'))]
        if not cleaned_lines:
            return []

        if not vocal_segments:
            return cls.auto_distribute_raw_lyrics(raw_text, total_duration)

        line_count = len(cleaned_lines)
        seg_count = len(vocal_segments)

        result = []

        if line_count <= seg_count:
            for idx, line in enumerate(cleaned_lines):
                seg_idx = int(idx * (seg_count / line_count))
                seg = vocal_segments[min(seg_idx, seg_count - 1)]
                result.append({
                    'line': line,
                    'start': seg['start'],
                    'end': seg['end']
                })
        else:
            lines_per_seg = math.ceil(line_count / seg_count)
            line_idx = 0

            for seg in vocal_segments:
                seg_lines = cleaned_lines[line_idx : line_idx + lines_per_seg]
                line_idx += lines_per_seg
                if not seg_lines:
                    break

                seg_dur = max(1.0, seg['end'] - seg['start'])
                sub_slot = seg_dur / len(seg_lines)

                for s_idx, s_line in enumerate(seg_lines):
                    start = round(seg['start'] + (s_idx * sub_slot), 2)
                    end = round(min(seg['end'], start + sub_slot * 0.95), 2)
                    result.append({
                        'line': s_line,
                        'start': start,
                        'end': end
                    })

        return result

    @classmethod
    def fetch_online_synced_lyrics(cls, title, artist=''):
        """
        Queries the free public LRCLIB database for 1-click synchronized lyrics.
        Returns dict with success status, lyrics_data list, and raw LRC content.
        """
        import urllib.request
        import urllib.parse
        import json

        title = str(title).strip()
        artist = str(artist).strip()

        if not title:
            return {'success': False, 'message': 'Please provide a song title.'}

        params = {'track_name': title}
        if artist:
            params['artist_name'] = artist

        url = f"https://lrclib.net/api/get?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'YTQuid/1.2.0 (contact@ytquid.app)'})

        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                synced = data.get('syncedLyrics', '')
                if synced:
                    parsed = cls.parse_lrc_file(synced)
                    return {
                        'success': True,
                        'is_synced': True,
                        'lyrics_data': parsed,
                        'lrc_text': synced,
                        'plain_lyrics': data.get('plainLyrics', ''),
                        'track_name': data.get('trackName', title),
                        'artist_name': data.get('artistName', artist)
                    }
        except Exception:
            pass

        query_str = f"{title} {artist}".strip()
        search_url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query_str)}"
        req_search = urllib.request.Request(search_url, headers={'User-Agent': 'YTQuid/1.2.0 (contact@ytquid.app)'})

        try:
            with urllib.request.urlopen(req_search, timeout=4) as resp:
                results = json.loads(resp.read().decode('utf-8'))
                for item in results:
                    synced = item.get('syncedLyrics')
                    if synced:
                        parsed = cls.parse_lrc_file(synced)
                        return {
                            'success': True,
                            'is_synced': True,
                            'lyrics_data': parsed,
                            'lrc_text': synced,
                            'plain_lyrics': item.get('plainLyrics', ''),
                            'track_name': item.get('trackName', title),
                            'artist_name': item.get('artistName', artist)
                        }

                if results and results[0].get('plainLyrics'):
                    return {
                        'success': True,
                        'is_synced': False,
                        'lyrics_data': [],
                        'plain_lyrics': results[0].get('plainLyrics'),
                        'track_name': results[0].get('trackName', title),
                        'artist_name': results[0].get('artistName', artist)
                    }
        except Exception as e:
            return {'success': False, 'message': f'Search query failed: {str(e)}'}

        return {'success': False, 'message': f'No synced lyrics found for "{title}". You can use Vocal Frequency Auto-Sync instead.'}

    @classmethod
    def format_words_into_lyric_bars(cls, words, max_words=7, max_chars=36, max_duration=4.2, min_pause=0.35):
        """
        Splits a continuous stream of timestamped words into clean, rhythmic song lyric bars (short lines).
        Uses vocal breath pauses, punctuation, word counts, and max duration to create optimal song bars.
        """
        if not words:
            return []

        bars = []
        current_bar_words = []

        for i, w in enumerate(words):
            current_bar_words.append(w)
            
            is_last = (i == len(words) - 1)
            if is_last:
                break

            next_w = words[i + 1]
            pause_after = max(0.0, next_w['start'] - w['end'])
            word_count = len(current_bar_words)
            char_len = sum(len(x['word']) for x in current_bar_words) + (word_count - 1)
            bar_dur = w['end'] - current_bar_words[0]['start']
            w_text = w['word'].strip()

            # Conditions to break into a new short lyric bar (line):
            # 1. Natural musical breath pause between words (e.g. >= 0.35s)
            is_pause_split = (pause_after >= min_pause and word_count >= 2) or (pause_after >= 0.6)
            # 2. Punctuation break after at least 3 words
            is_punct_split = (w_text.endswith((',', '.', '!', '?', ';', ':', '—', '-')) and word_count >= 3)
            # 3. Maximum words per line (4 to 7 words is ideal for music bars)
            is_length_split = (word_count >= max_words) or (char_len >= max_chars)
            # 4. Maximum duration cap
            is_duration_split = (bar_dur >= max_duration and word_count >= 3)

            if is_pause_split or is_punct_split or is_length_split or is_duration_split:
                bar_start = round(current_bar_words[0]['start'], 2)
                bar_end = round(max(current_bar_words[-1]['end'], bar_start + 0.8), 2)
                if next_w['start'] > bar_end:
                    bar_end = round(min(next_w['start'], bar_end + 0.4), 2)

                bar_line = " ".join(x['word'].strip() for x in current_bar_words).strip()
                if bar_line:
                    bars.append({
                        'line': bar_line,
                        'start': bar_start,
                        'end': bar_end,
                        'words': list(current_bar_words)
                    })
                current_bar_words = []

        # Flush any trailing words
        if current_bar_words:
            bar_start = round(current_bar_words[0]['start'], 2)
            bar_end = round(max(current_bar_words[-1]['end'], bar_start + 1.0), 2)
            bar_line = " ".join(x['word'].strip() for x in current_bar_words).strip()
            if bar_line:
                bars.append({
                    'line': bar_line,
                    'start': bar_start,
                    'end': bar_end,
                    'words': list(current_bar_words)
                })

        # Smooth out transitions and eliminate timestamp overlaps
        for idx in range(len(bars)):
            if idx + 1 < len(bars):
                next_start = bars[idx + 1]['start']
                if bars[idx]['end'] > next_start:
                    bars[idx]['end'] = round(next_start, 2)
                elif next_start - bars[idx]['end'] < 0.6:
                    bars[idx]['end'] = round(next_start, 2)

        return bars

    @classmethod
    def transcribe_and_sync_with_whisper(cls, audio_path, model_size='base', initial_prompt=None):
        """
        Uses local Whisper AI (faster-whisper) with word-level timestamping
        to automatically transcribe speech/singing and generate short, rhythmic song lyric bars.
        Works 100% offline for any song (AI generated, Suno, Udio, unreleased tracks, or commercial).
        """
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError("faster-whisper is not installed. Please install it with: pip install faster-whisper")

        audio_path = os.path.abspath(str(audio_path))
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Choose efficient INT8 quantization on CPU
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        
        # Transcribe with word timestamps and VAD filter to ignore silence
        prompt_text = initial_prompt or "Song lyrics formatted in short musical bars and rhyming verse lines."
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=350),
            initial_prompt=prompt_text
        )

        all_words = []

        for seg in segments:
            if seg.words:
                for w in seg.words:
                    clean_w = w.word.strip()
                    if clean_w:
                        all_words.append({
                            'word': clean_w,
                            'start': round(w.start, 2),
                            'end': round(w.end, 2)
                        })
            elif seg.text and seg.text.strip():
                # Fallback: estimate word timestamps if word-level missing
                words_list = seg.text.strip().split()
                dur = max(0.5, seg.end - seg.start)
                slot = dur / len(words_list)
                for s_idx, wt in enumerate(words_list):
                    all_words.append({
                        'word': wt,
                        'start': round(seg.start + s_idx * slot, 2),
                        'end': round(seg.start + (s_idx + 1) * slot, 2)
                    })

        # Format all timestamped words into clean, short song lyric bars (4-7 words per line)
        lyrics_data = cls.format_words_into_lyric_bars(all_words, max_words=7, max_chars=36)
        plain_lines = [b['line'] for b in lyrics_data]

        return {
            'success': True,
            'lyrics_data': lyrics_data,
            'plain_lyrics': "\n".join(plain_lines),
            'detected_language': info.language,
            'language_probability': round(getattr(info, 'language_probability', 1.0), 2),
            'duration': round(getattr(info, 'duration', 0.0), 2)
        }

    @classmethod
    def hex_to_ass_color(cls, hex_str, alpha=0):
        """
        Converts hex color (e.g. #00E5FF or #FFFFFF) to ASS color format &HAABBGGRR&.
        """
        hex_str = hex_str.lstrip('#')
        if len(hex_str) == 3:
            hex_str = "".join([c * 2 for c in hex_str])
        if len(hex_str) != 6:
            hex_str = "FFFFFF"

        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
        a = max(0, min(255, int(alpha)))

        # ASS uses &HAABBGGRR (Blue, Green, Red)
        return f"&H{a:02X}{b:02X}{g:02X}{r:02X}&"

    @classmethod
    def seconds_to_ass_time(cls, seconds):
        """
        Converts seconds float to ASS time format: H:MM:SS.cs
        """
        sec = max(0.0, float(seconds))
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        cs = int(round((sec - int(sec)) * 100))
        if cs >= 100:
            cs = 99
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    @classmethod
    def generate_ass_subtitles(
        cls,
        lyrics_data,
        output_ass_path,
        aspect_ratio='16:9',
        animation_style='KARAOKE_WIPE',
        font_family='Arial',
        font_size=48,
        highlight_color='#00E5FF',
        text_color='#FFFFFF',
        position_mode='CENTER'
    ):
        """
        Generates Advanced SubStation Alpha (.ass) subtitle file with karaoke wipes,
        glowing typography, drop shadows, and multi-line animations.
        """
        is_vertical = (aspect_ratio == '9:16')
        res_x = 1080 if is_vertical else 1920
        res_y = 1920 if is_vertical else 1080

        # Adjust default font size for canvas
        if is_vertical:
            actual_font_size = int(font_size * 1.15)
            margin_lr = 60
            if position_mode == 'BOTTOM':
                margin_v = 240
            elif position_mode == 'TOP':
                margin_v = 240
            else:
                margin_v = 450
        else:
            actual_font_size = int(font_size)
            margin_lr = 120
            if position_mode == 'BOTTOM':
                margin_v = 120
            elif position_mode == 'TOP':
                margin_v = 120
            else:
                margin_v = 280

        # ASS alignment: 2 = Bottom-Center, 5 = Mid-Center, 8 = Top-Center
        if position_mode == 'TOP':
            alignment = 8
        elif position_mode == 'CENTER':
            alignment = 5
        else:
            alignment = 2

        # Primary = Active Highlight Color; Secondary = Inactive Text Color (Wipe effect)
        primary_ass = cls.hex_to_ass_color(highlight_color, alpha=0)
        secondary_ass = cls.hex_to_ass_color(text_color, alpha=0)
        outline_ass = cls.hex_to_ass_color('#000000', alpha=40)
        shadow_ass = cls.hex_to_ass_color('#000000', alpha=120)
        dimmed_ass = cls.hex_to_ass_color(text_color, alpha=160)

        # Specific styling presets
        if animation_style == 'CYBER_NEON':
            primary_ass = cls.hex_to_ass_color(highlight_color or '#00FFEA', alpha=0)
            secondary_ass = cls.hex_to_ass_color('#0F2A3F', alpha=20)
            outline_ass = cls.hex_to_ass_color(highlight_color or '#00FFEA', alpha=80)
            outline_width = 3.5
            shadow_depth = 0
            bold_val = 1
        elif animation_style == 'CINEMATIC':
            primary_ass = cls.hex_to_ass_color(highlight_color or '#F8F9FA', alpha=0)
            secondary_ass = cls.hex_to_ass_color('#A0AEC0', alpha=60)
            outline_ass = cls.hex_to_ass_color('#000000', alpha=100)
            outline_width = 1.5
            shadow_depth = 2.0
            bold_val = 0
            if font_family == 'Arial':
                font_family = 'Georgia'
        else:
            # KARAOKE_WIPE & ROLLING_3LINE defaults
            outline_width = 2.5
            shadow_depth = 2.0
            bold_val = 1

        script_content = [
            "[Script Info]",
            "Title: YT Quid Synced Lyrics",
            "ScriptType: v4.00+",
            "WrapStyle: 0",
            f"PlayResX: {res_x}",
            f"PlayResY: {res_y}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            # Main Style
            f"Style: Main,{font_family},{actual_font_size},{primary_ass},{secondary_ass},{outline_ass},{shadow_ass},{bold_val},0,0,0,100,100,0,0,1,{outline_width},{shadow_depth},{alignment},{margin_lr},{margin_lr},{margin_v},1",
            # Dimmed Rolling Style
            f"Style: RollingDim,{font_family},{int(actual_font_size * 0.78)},{dimmed_ass},{dimmed_ass},{outline_ass},{shadow_ass},0,0,0,0,100,100,0,0,1,1.5,1.0,{alignment},{margin_lr},{margin_lr},{margin_v},1",
            # Neon Glow Style
            f"Style: NeonGlow,{font_family},{actual_font_size},{primary_ass},{secondary_ass},{outline_ass},{shadow_ass},1,0,0,0,100,100,1,0,1,4.0,0,{alignment},{margin_lr},{margin_lr},{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        # Generate Dialogue Events
        for idx, item in enumerate(lyrics_data):
            raw_line = str(item.get('line', '')).strip()
            if not raw_line:
                continue

            start_sec = float(item.get('start', 0.0))
            end_sec = float(item.get('end', start_sec + 4.0))
            if end_sec <= start_sec:
                end_sec = start_sec + 2.0

            start_time_str = cls.seconds_to_ass_time(start_sec)
            end_time_str = cls.seconds_to_ass_time(end_sec)
            duration_cs = max(10, int((end_sec - start_sec) * 100))

            if animation_style == 'KARAOKE_WIPE':
                # Check if exact word timestamps are provided
                words_list = item.get('words')
                if words_list and len(words_list) > 0:
                    karaoke_text_parts = []
                    for w in words_list:
                        w_text = w.get('word', '')
                        w_start = float(w.get('start', start_sec))
                        w_end = float(w.get('end', w_start + 0.3))
                        w_cs = max(5, int((w_end - w_start) * 100))
                        karaoke_text_parts.append(f"{{\\k{w_cs}}}{w_text}")
                    karaoke_line = " ".join(karaoke_text_parts)
                else:
                    # Fallback proportional word wipe
                    words = raw_line.split(' ')
                    total_chars = max(1, sum(len(w) for w in words))
                    karaoke_text_parts = []
                    for w in words:
                        w_cs = max(8, int(duration_cs * (len(w) / total_chars)))
                        karaoke_text_parts.append(f"{{\\k{w_cs}}}{w}")
                    karaoke_line = " ".join(karaoke_text_parts)

                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{karaoke_line}"
                )

                if position_mode == 'TOP':
                    y_center = margin_v + int(actual_font_size * 1.5)
                elif position_mode == 'CENTER':
                    y_center = res_y // 2
                else:
                    y_center = res_y - margin_v - int(actual_font_size * 0.5)
                y_prev = y_center - int(actual_font_size * 1.5)
                y_next = y_center + int(actual_font_size * 1.5)
                x_center = res_x // 2

                # 1. Previous line (if exists)
                if idx > 0 and lyrics_data[idx - 1].get('line'):
                    prev_text = lyrics_data[idx - 1]['line']
                    script_content.append(
                        f"Dialogue: 0,{start_time_str},{end_time_str},RollingDim,,0,0,0,,{{\\pos({x_center},{y_prev})\\fad(150,150)}}{prev_text}"
                    )

                # 2. Current active line (highlighted + karaoke wipe or pulse)
                script_content.append(
                    f"Dialogue: 1,{start_time_str},{end_time_str},Main,,0,0,0,,{{\\pos({x_center},{y_center})\\fad(100,100)}}{raw_line}"
                )

                # 3. Next line preview (if exists)
                if idx + 1 < len(lyrics_data) and lyrics_data[idx + 1].get('line'):
                    next_text = lyrics_data[idx + 1]['line']
                    script_content.append(
                        f"Dialogue: 0,{start_time_str},{end_time_str},RollingDim,,0,0,0,,{{\\pos({x_center},{y_next})\\fad(150,150)}}{next_text}"
                    )

            elif animation_style == 'CYBER_NEON':
                # Glowing Cyber Neon with glowing border blur and fade
                words = raw_line.split(' ')
                total_chars = max(1, sum(len(w) for w in words))
                k_parts = [f"{{\\k{max(8, int(duration_cs * (len(w)/total_chars)))}}}{w}" for w in words]
                neon_line = " ".join(k_parts)
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},NeonGlow,,0,0,0,,{{\\blur2\\fad(120,120)}}{neon_line}"
                )

            elif animation_style == 'CINEMATIC':
                # Smooth, elegant fade with subtle serif display
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{{\\fad(280,280)}}{raw_line}"
                )
            else:
                # Default clean display
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{raw_line}"
                )

        os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
        with open(output_ass_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(script_content))

        return output_ass_path

    @classmethod
    def generate_ambient_background_frame(cls, background_image_path, width, height, output_frame_path):
        """
        Creates a high-resolution ambient background frame with smooth Gaussian blur,
        dark vignette enhancement, and centered cover art if provided.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_frame_path)), exist_ok=True)

        if background_image_path and os.path.exists(background_image_path):
            img = Image.open(background_image_path).convert('RGB')
            # 1. Ambient blurred background
            bg = img.resize((width, height), Image.Resampling.LANCZOS)
            bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
            enhancer = ImageEnhance.Brightness(bg)
            bg = enhancer.enhance(0.35)

            # 2. Centered album artwork with rounded corner effect & shadow
            target_art_size = int(min(width, height) * 0.42)
            art_thumb = img.resize((target_art_size, target_art_size), Image.Resampling.LANCZOS)
            
            pos_x = (width - target_art_size) // 2
            # Center vertically or shift slightly up to make room for lyrics
            pos_y = int((height - target_art_size) * 0.30) if height > width else int((height - target_art_size) * 0.25)
            
            # Paste art onto background
            bg.paste(art_thumb, (pos_x, pos_y))
            bg.save(output_frame_path, 'JPEG', quality=95)
        else:
            # Generate sleek dark gradient background
            img = Image.new('RGB', (width, height), color=(10, 14, 23))
            draw = ImageDraw.Draw(img)
            
            # Subtle radial glow
            center_x, center_y = width // 2, height // 2
            max_radius = int(math.hypot(center_x, center_y))
            
            for r in range(max_radius, 0, -15):
                alpha = int(35 * (1 - r / max_radius))
                color = (15 + alpha // 2, 22 + alpha, 38 + int(alpha * 1.5))
                draw.ellipse(
                    [center_x - r, center_y - r, center_x + r, center_y + r],
                    fill=color
                )
            
            img.save(output_frame_path, 'JPEG', quality=95)

        return output_frame_path

    @classmethod
    def render_lyrics_video(
        cls,
        audio_path,
        background_image_path=None,
        background_video_path=None,
        lyrics_data=None,
        output_video_path=None,
        aspect_ratio='16:9',
        animation_style='KARAOKE_WIPE',
        font_family='Arial',
        font_size=48,
        highlight_color='#00E5FF',
        text_color='#FFFFFF',
        position_mode='CENTER',
        title='Lyric Video',
        artist=''
    ):
        """
        Renders complete 1080p synchronized lyric video using local FFmpeg and ASS subtitle engine.
        """
        ffmpeg = cls.get_ffmpeg_binary()
        audio_path = os.path.abspath(str(audio_path))
        output_video_path = os.path.abspath(str(output_video_path))
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        duration = cls.inspect_media_duration(audio_path)
        if duration <= 0:
            duration = 60.0

        is_vertical = (aspect_ratio == '9:16')
        width = 1080 if is_vertical else 1920
        height = 1920 if is_vertical else 1080

        # Create temporary working directory for subtitle and frame assets
        temp_dir = os.path.join(os.path.dirname(output_video_path), f"temp_lyrics_{os.getpid()}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            # 1. Prepare ASS Subtitles
            ass_path = os.path.join(temp_dir, "lyrics.ass")
            cls.generate_ass_subtitles(
                lyrics_data=lyrics_data or [],
                output_ass_path=ass_path,
                aspect_ratio=aspect_ratio,
                animation_style=animation_style,
                font_family=font_family,
                font_size=font_size,
                highlight_color=highlight_color,
                text_color=text_color,
                position_mode=position_mode
            )

            # Escape subtitle path for FFmpeg filter on Windows
            escaped_ass_path = ass_path.replace('\\', '/').replace(':', '\\:')

            # 2. Build FFmpeg command depending on background source
            if background_video_path and os.path.exists(background_video_path):
                bg_vid = os.path.abspath(str(background_video_path))
                # Loop background video to audio duration and burn in subtitles
                vf_filter = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"ass='{escaped_ass_path}'"
                )
                cmd = [
                    ffmpeg, '-y',
                    '-stream_loop', '-1',
                    '-i', bg_vid,
                    '-i', audio_path,
                    '-vf', vf_filter,
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '20',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-t', str(duration),
                    '-movflags', '+faststart',
                    output_video_path
                ]
            else:
                # Prepare background image frame
                frame_path = os.path.join(temp_dir, "bg_frame.jpg")
                cls.generate_ambient_background_frame(
                    background_image_path=background_image_path,
                    width=width,
                    height=height,
                    output_frame_path=frame_path
                )

                vf_filter = f"ass='{escaped_ass_path}'"
                cmd = [
                    ffmpeg, '-y',
                    '-loop', '1',
                    '-framerate', '30',
                    '-i', frame_path,
                    '-i', audio_path,
                    '-vf', vf_filter,
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '20',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-t', str(duration),
                    '-movflags', '+faststart',
                    output_video_path
                ]

            # Execute rendering command
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors='ignore'
            )

            if proc.returncode != 0 or not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
                raise RuntimeError(f"FFmpeg lyric video render failed: {proc.stderr[-1000:]}")

            return {
                'success': True,
                'output_video': output_video_path,
                'duration': duration
            }

        finally:
            # Clean up temporary working directory
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
