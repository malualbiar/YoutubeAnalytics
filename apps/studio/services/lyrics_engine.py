import os
import sys
import shutil
import glob
import subprocess
import math
import re
import time
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw, ImageFont

from django.conf import settings
from .renderer import VideoStudioRenderer
from .process_tracker import RenderProcessTracker

class LyricsEngineService:

    @classmethod
    def get_ffmpeg_binary(cls):
        return VideoStudioRenderer.get_ffmpeg_binary()

    @classmethod
    def get_subprocess_kwargs(cls):
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        return kwargs

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
    def normalize_vocal_segments(cls, vocal_segments, min_gap=0.75, min_duration=1.0):
        """
        Merge nearby vocal phrases split by brief breaths or tiny instrumental gaps,
        while rejecting fragments too short to represent a sung phrase.
        """
        if not vocal_segments:
            return []

        normalized = []
        for segment in sorted(vocal_segments, key=lambda s: s.get('start', 0.0)):
            start = float(segment.get('start', 0.0))
            end = float(segment.get('end', start))
            duration = max(0.0, end - start)

            if normalized and (start - normalized[-1]['end']) <= min_gap:
                normalized[-1]['end'] = max(normalized[-1]['end'], end)
                normalized[-1]['duration'] = round(normalized[-1]['end'] - normalized[-1]['start'], 2)
            else:
                normalized.append({
                    'start': round(start, 2),
                    'end': round(end, 2),
                    'duration': round(duration, 2)
                })

        filtered = []
        for segment in normalized:
            duration = max(0.0, segment['end'] - segment['start'])
            if duration >= min_duration:
                filtered.append(segment)

        return filtered

    @classmethod
    def detect_vocal_segments(cls, audio_path, min_silence_duration=0.35, noise_threshold_db=-35):
        """
        Uses vocal frequency bandpass filtering (300Hz-3400Hz) and silence detection
        to identify active vocal singing segments vs instrumental intros, solos & breaks.
        Returns list of dicts:
        [{'start': 12.4, 'end': 16.8, 'duration': 4.4}, ...]
        """
        ffmpeg = cls.get_ffmpeg_binary()
        audio_path = os.path.abspath(str(audio_path))
        total_duration = cls.inspect_media_duration(audio_path)

        # 1. Focus on the vocal formant band while trimming obvious low-end percussion energy.
        # 2. Use a stricter gain curve so kick/snare transients do not dominate the result.
        # 3. Silence detector is then applied to sustained vocal-like activity instead of broad mix energy.
        af_filter = (
            f"highpass=f=120,"
            f"lowpass=f=3000,"
            f"compand=attacks=0.02:decays=0.12:points=-70/-70|-30/-12|-10/-3|0/0,"
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

            valid_segments = [s for s in vocal_segments if s['duration'] >= 0.9]
            valid_segments = cls.normalize_vocal_segments(valid_segments)
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
                seg_dur = max(1.0, seg['end'] - seg['start'])
                lead_in = seg_dur * 0.16
                start = round(seg['start'] + lead_in, 2)
                end = round(min(seg['end'], seg['start'] + seg_dur * 0.9), 2)
                if end <= start:
                    end = round(min(seg['end'], start + 0.9), 2)
                result.append({
                    'line': line,
                    'start': start,
                    'end': end
                })
        else:
            lines_left = line_count
            for seg_idx, seg in enumerate(vocal_segments):
                if lines_left <= 0:
                    break

                remaining_slots = max(1, seg_count - seg_idx)
                target_lines = max(1, math.ceil(lines_left / remaining_slots))
                seg_lines = cleaned_lines[len(result):len(result) + target_lines]
                if not seg_lines:
                    break

                seg_dur = max(1.0, seg['end'] - seg['start'])
                phrase_start = seg['start'] + (seg_dur * 0.18)
                usable_dur = max(0.8, seg['end'] - phrase_start)
                sub_slot = usable_dur / len(seg_lines)

                for s_idx, s_line in enumerate(seg_lines):
                    start = round(phrase_start + (s_idx * sub_slot), 2)
                    end = round(min(seg['end'], start + max(0.9, sub_slot * 0.9)), 2)
                    if end <= start:
                        end = round(min(seg['end'], start + 0.9), 2)
                    result.append({
                        'line': s_line,
                        'start': start,
                        'end': end
                    })

                lines_left -= len(seg_lines)

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

        def flush_bar(bar_words):
            if not bar_words:
                return
            bar_start = round(bar_words[0]['start'], 2)
            bar_end = round(max(bar_words[-1]['end'], bar_start + 0.8), 2)
            line = " ".join(x['word'].strip() for x in bar_words).strip()
            if line:
                bars.append({
                    'line': line,
                    'start': bar_start,
                    'end': bar_end,
                    'words': list(bar_words)
                })

        for i, w in enumerate(words):
            if not current_bar_words:
                current_bar_words = [w]
                continue

            prev_w = current_bar_words[-1]
            pause_after = max(0.0, w['start'] - prev_w['end'])
            word_count = len(current_bar_words) + 1
            char_len = sum(len(x['word']) for x in current_bar_words) + len(w['word']) + (word_count - 1)
            bar_dur = w['end'] - current_bar_words[0]['start']
            prev_text = prev_w['word'].strip()

            is_pause_split = (pause_after >= min_pause and len(current_bar_words) >= 2) or (pause_after >= 0.6)
            is_punct_split = prev_text.endswith((',', '.', '!', '?', ';', ':', '—', '-')) and len(current_bar_words) >= 2
            is_length_split = (word_count > max_words) or (char_len >= max_chars)
            is_duration_split = (bar_dur >= max_duration and len(current_bar_words) >= 2)

            if is_pause_split or is_punct_split or is_length_split or is_duration_split:
                flush_bar(current_bar_words)
                current_bar_words = []

            current_bar_words.append(w)

        flush_bar(current_bar_words)

        # Trim bar end times and inject ♪ instrumental placeholders for gaps
        # longer than this threshold — these are intros, solos, and bridges
        # where no vocals are present. Without this, the screen is blank for
        # potentially 20–30 seconds with no feedback to the viewer.
        INSTRUMENTAL_GAP_THRESHOLD = 4.0  # seconds

        filled = []
        for idx in range(len(bars)):
            bar = bars[idx]

            if idx + 1 < len(bars):
                next_start = bars[idx + 1]['start']
                # Clamp overlapping or nearly-adjacent bar ends
                if bar['end'] > next_start:
                    bar['end'] = round(next_start, 2)
                elif next_start - bar['end'] < 0.6:
                    bar['end'] = round(next_start, 2)

                filled.append(bar)

                # Insert instrumental placeholder if the gap to the next bar
                # is long enough to be a meaningful instrumental section
                gap = bars[idx + 1]['start'] - bar['end']
                if gap >= INSTRUMENTAL_GAP_THRESHOLD:
                    instr_start = round(bar['end'] + 0.3, 2)
                    instr_end = round(bars[idx + 1]['start'] - 0.3, 2)
                    if instr_end > instr_start:
                        filled.append({
                            'line': '♪',
                            'start': instr_start,
                            'end': instr_end,
                            'words': []
                        })
            else:
                filled.append(bar)

        return filled

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

        # If input is a video file, pre-extract audio to a clean 16kHz mono WAV.
        # This avoids codec issues and ensures Whisper processes the complete audio track.
        _video_exts = {'.mp4', '.mov', '.mkv', '.webm', '.avi', '.m4v', '.flv'}
        extracted_wav = None
        if os.path.splitext(audio_path)[1].lower() in _video_exts:
            import tempfile
            ffmpeg = cls.get_ffmpeg_binary()
            tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            tmp.close()
            extracted_wav = tmp.name
            cmd = [
                ffmpeg, '-y', '-i', audio_path,
                '-vn',                # drop video stream
                '-ac', '1',          # mono
                '-ar', '16000',      # 16kHz — Whisper's native rate
                '-c:a', 'pcm_s16le', # uncompressed WAV
                extracted_wav
            ]
            result = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            if result.returncode != 0 or not os.path.exists(extracted_wav):
                # Fallback: pass the original file directly
                extracted_wav = None
            else:
                audio_path = extracted_wav

        try:
            from difflib import SequenceMatcher

            # Choose efficient INT8 quantization on CPU
            model = WhisperModel(model_size, device="cpu", compute_type="int8")

            # VAD filter is disabled for music — it silences instrumental sections,
            # reverb tails, and quiet passages, causing whole verses to be dropped.
            # condition_on_previous_text=False prevents hallucination loops.
            # no_speech_threshold lowered to 0.3 so filler vocalizations (hmm, ohh,
            # ah) are not silently dropped — they sit at the edge of Whisper's
            # speech/music classifier and a threshold of 0.5 kills them.
            prompt_text = initial_prompt if initial_prompt else "Lyrics:"
            segments, info = model.transcribe(
                audio_path,
                beam_size=5,
                word_timestamps=True,
                vad_filter=False,
                condition_on_previous_text=False,
                no_speech_threshold=0.3,
                initial_prompt=prompt_text
            )

            all_words = []
            _prompt_lower = prompt_text.lower().strip().rstrip(':').strip()

            # Known Whisper hallucination phrases — only exact full-segment matches
            _HALLUCINATION_PHRASES = {
                "song lyrics formatted in short musical bars and rhyming verse lines",
                "lyrics formatted in short musical bars and rhyming verse lines",
                "thank you for watching",
                "thanks for watching",
                "please subscribe",
                "like and subscribe",
                "subtitles by",
                "transcribed by",
            }

            def _is_hallucination(text):
                t = text.lower().strip().rstrip('.')
                if t in _HALLUCINATION_PHRASES:
                    return True
                if _prompt_lower and t == _prompt_lower:
                    return True
                return False

            # Fuzzy repeat suppression — real hallucination loops repeat 10-20+
            # times with near-identical text. Real choruses repeat 2-4 times and
            # often have minor variation. We suppress only when:
            #   - similarity ratio > 0.92 (nearly identical text)
            #   - AND the run has repeated 5+ consecutive times
            # This prevents the old threshold-of-3 from killing genuine chorus lines.
            _repeat_text = None
            _repeat_count = 0

            def _is_hallucination_loop(text):
                nonlocal _repeat_text, _repeat_count
                if _repeat_text is None:
                    _repeat_text = text
                    _repeat_count = 1
                    return False
                ratio = SequenceMatcher(None, text.lower(), _repeat_text.lower()).ratio()
                if ratio > 0.92:
                    _repeat_count += 1
                else:
                    _repeat_text = text
                    _repeat_count = 1
                return _repeat_count >= 5

            # Whisper emits music-note tokens (♪, ♫) and transcribes filler sounds
            # like "hmm", "mm", "oh", "ah" as real words. We preserve them all —
            # stripping them was the original cause of missing fillers.
            # Only strip pure-whitespace tokens.
            for seg in segments:
                seg_text = seg.text.strip() if seg.text else ''
                if not seg_text:
                    continue

                if _is_hallucination(seg_text):
                    continue

                if _is_hallucination_loop(seg_text):
                    continue

                if seg.words:
                    for w in seg.words:
                        # Preserve the raw token — only skip truly empty strings.
                        # This keeps ♪, hmm, oh, ah, mm intact.
                        raw_w = w.word.strip()
                        if raw_w:
                            all_words.append({
                                'word': raw_w,
                                'start': round(w.start, 2),
                                'end': round(w.end, 2)
                            })
                else:
                    words_list = seg_text.split()
                    dur = max(0.5, seg.end - seg.start)
                    slot = dur / len(words_list)
                    for s_idx, wt in enumerate(words_list):
                        all_words.append({
                            'word': wt,
                            'start': round(seg.start + s_idx * slot, 2),
                            'end': round(seg.start + (s_idx + 1) * slot, 2)
                        })

            # Format all timestamped words into clean, short song lyric bars
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
        finally:
            # Clean up temp extracted WAV if we created one from a video file
            if extracted_wav and os.path.exists(extracted_wav):
                try:
                    os.remove(extracted_wav)
                except Exception:
                    pass

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
        position_mode='CENTER',
        font_weight='bold',
        font_italic=False,
        letter_spacing=0.0,
        line_height=1.4,
        text_transform='none',
        text_stroke_width=2.5,
        text_shadow_depth=2.0,
        font_scale_x=100,
        font_scale_y=100,
        bg_opacity=0
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

        # Base weight/italic extraction
        italic_val = 1 if font_italic else 0
        bold_val = 1 if font_weight in ('bold', 'black') else 0
        
        # Override presets with new typography fields
        outline_width = text_stroke_width
        shadow_depth = text_shadow_depth
        bg_color_ass = cls.hex_to_ass_color('#000000', alpha=int(255 - (bg_opacity * 2.55)))
        border_style = 3 if bg_opacity > 0 else 1

        # Specific styling presets (adjusting defaults for certain styles if needed)
        if animation_style == 'CYBER_NEON':
            primary_ass = cls.hex_to_ass_color(highlight_color or '#00FFEA', alpha=0)
            secondary_ass = cls.hex_to_ass_color('#0F2A3F', alpha=20)
            outline_ass = cls.hex_to_ass_color(highlight_color or '#00FFEA', alpha=80)
            outline_width = max(3.5, text_stroke_width)
            shadow_depth = 0
        elif animation_style == 'CINEMATIC':
            primary_ass = cls.hex_to_ass_color(highlight_color or '#F8F9FA', alpha=0)
            secondary_ass = cls.hex_to_ass_color('#A0AEC0', alpha=60)
            outline_ass = cls.hex_to_ass_color('#000000', alpha=100)
            bold_val = 0 if font_weight in ('normal', 'light') else bold_val
            if font_family == 'Arial':
                font_family = 'Georgia'

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
            f"Style: Main,{font_family},{actual_font_size},{primary_ass},{secondary_ass},{outline_ass},{bg_color_ass},{bold_val},{italic_val},0,0,{font_scale_x},{font_scale_y},{letter_spacing},0,{border_style},{outline_width},{shadow_depth},{alignment},{margin_lr},{margin_lr},{margin_v},1",
            # Dimmed Rolling Style
            f"Style: RollingDim,{font_family},{int(actual_font_size * 0.78)},{dimmed_ass},{dimmed_ass},{outline_ass},{bg_color_ass},{bold_val},{italic_val},0,0,{font_scale_x},{font_scale_y},{letter_spacing},0,{border_style},{max(0.5, outline_width*0.5)},{max(0.5, shadow_depth*0.5)},{alignment},{margin_lr},{margin_lr},{margin_v},1",
            # Neon Glow Style
            f"Style: NeonGlow,{font_family},{actual_font_size},{primary_ass},{secondary_ass},{outline_ass},{bg_color_ass},{bold_val},{italic_val},0,0,{font_scale_x},{font_scale_y},{letter_spacing},0,{border_style},{outline_width},{shadow_depth},{alignment},{margin_lr},{margin_lr},{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ]

        # Generate Dialogue Events
        for idx, item in enumerate(lyrics_data):
            raw_line = str(item.get('line', '')).strip()
            if not raw_line:
                continue

            # Instrumental placeholder — render as a dimmed, centred ♪ with a
            # slow fade regardless of the chosen animation style. Skip transforms.
            if raw_line == '♪':
                instr_color = cls.hex_to_ass_color(text_color, alpha=160)
                script_content.append(
                    f"Dialogue: 0,{cls.seconds_to_ass_time(float(item.get('start', 0.0)))},"
                    f"{cls.seconds_to_ass_time(float(item.get('end', float(item.get('start', 0.0)) + 4.0)))},"
                    f"RollingDim,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center})\\c{instr_color}\\fad(400,400)}}♪"
                )
                continue

            # Apply Text Transform
            if text_transform == 'uppercase':
                raw_line = raw_line.upper()
            elif text_transform == 'lowercase':
                raw_line = raw_line.lower()
            elif text_transform == 'capitalize':
                raw_line = raw_line.title()

            start_sec = float(item.get('start', 0.0))
            end_sec = float(item.get('end', start_sec + 4.0))
            if end_sec <= start_sec:
                end_sec = start_sec + 2.0

            start_time_str = cls.seconds_to_ass_time(start_sec)
            end_time_str = cls.seconds_to_ass_time(end_sec)
            duration_cs = max(10, int((end_sec - start_sec) * 100))

            # Helper for line positions
            x_center = res_x // 2
            if position_mode == 'TOP':
                y_center = margin_v + int(actual_font_size * 1.5)
            elif position_mode == 'CENTER':
                y_center = res_y // 2
            else:
                y_center = res_y - margin_v - int(actual_font_size * 0.5)
            
            # Apply dynamic line_height setting
            y_prev = y_center - int(actual_font_size * line_height)
            y_next = y_center + int(actual_font_size * line_height)

            # Auto-synchronize word-level timestamps with edited line spellings
            line_words_tokens = raw_line.split()
            words_list = item.get('words')
            if line_words_tokens:
                if words_list and len(words_list) == len(line_words_tokens):
                    # Preserve exact Whisper millisecond timings while updating corrected spelling
                    words_list = [
                        {
                            'word': line_words_tokens[w_i],
                            'start': words_list[w_i].get('start', start_sec),
                            'end': words_list[w_i].get('end', end_sec)
                        }
                        for w_i in range(len(line_words_tokens))
                    ]
                elif words_list and len(words_list) != len(line_words_tokens):
                    # Resynchronize redistributed words across line duration
                    dur = max(0.4, end_sec - start_sec)
                    slot = dur / len(line_words_tokens)
                    words_list = [
                        {
                            'word': wt,
                            'start': round(start_sec + w_i * slot, 2),
                            'end': round(start_sec + (w_i + 1) * slot, 2)
                        }
                        for w_i, wt in enumerate(line_words_tokens)
                    ]

            if animation_style == 'KARAOKE_WIPE':
                # Entry: soft fade-in + blur that clears on the first beat so the
                # line doesn't hard-cut into view. Exit: short fade-out.
                # The \k wipe runs across the full duration as before.
                if words_list and len(words_list) > 0:
                    k_parts = []
                    for w in words_list:
                        w_text = w.get('word', '')
                        w_cs = max(5, int((float(w.get('end', float(w.get('start', start_sec)) + 0.3)) - float(w.get('start', start_sec))) * 100))
                        k_parts.append(f"{{\\k{w_cs}}}{w_text}")
                    karaoke_line = " ".join(k_parts)
                else:
                    words = raw_line.split(' ')
                    total_chars = max(1, sum(len(w) for w in words))
                    karaoke_line = " ".join([f"{{\\k{max(8, int(duration_cs * (len(w) / total_chars)))}}}{w}" for w in words])
                entry_tag = f"{{\\pos({x_center},{y_center})\\blur2\\t(0,120,\\blur0)\\fad(80,80)}}"
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{entry_tag}{karaoke_line}")

            elif animation_style == 'PLAYFUL_POP':
                # Spring bounce entry + confetti burst of ✦ · ★ particles.
                # Each confetti glyph gets a unique position offset, scale, and
                # staggered start so they scatter outward on the beat of entry.
                duration_ms = duration_cs * 10
                exit_start_ms = max(200, duration_ms - 200)
                s_x = font_scale_x
                s_y = font_scale_y
                pop_tag = (
                    f"{{\\pos({x_center},{y_center})"
                    f"\\fscx{int(s_x * 0.5)}\\fscy{int(s_y * 0.5)}\\alpha&HFF&"
                    f"\\t(0,120,\\fscx{int(s_x * 1.18)}\\fscy{int(s_y * 1.18)}\\alpha&H00&)"
                    f"\\t(120,220,\\fscx{int(s_x * 0.95)}\\fscy{int(s_y * 0.95)})"
                    f"\\t(220,300,\\fscx{s_x}\\fscy{s_y})"
                    f"\\t({exit_start_ms},{duration_ms},\\fscx{int(s_x * 0.4)}\\fscy{int(s_y * 0.4)}\\alpha&HFF&)}}"
                )
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{pop_tag}{raw_line}")

                # Confetti particles — scatter outward from text center on entry,
                # each fades out over ~400ms. Positions/sizes use a deterministic
                # pattern seeded by line index so every line gets a unique burst.
                confetti_glyphs = ['✦', '✧', '·', '★', '✦', '·', '✧', '★', '·', '✦']
                confetti_offsets = [
                    (-110, -35), ( 120, -28), (-80,  30), ( 90,  38),
                    (-145, -10), ( 148,  12), (-50, -48), ( 55, -44),
                    (-30,  50), (  35,  52),
                ]
                confetti_scales = [55, 40, 30, 60, 35, 28, 50, 45, 25, 38]
                confetti_colors = [
                    highlight_color, '#FFFFFF', highlight_color, '#FFFFFF',
                    highlight_color, '#FFFFFF', highlight_color, '#FFFFFF',
                    highlight_color, '#FFFFFF',
                ]
                for p_i, (glyph, (ox, oy), scale, color) in enumerate(zip(
                    confetti_glyphs, confetti_offsets, confetti_scales, confetti_colors
                )):
                    p_delay_ms = p_i * 18   # stagger each particle by 18ms
                    p_x = x_center + ox + ((idx * 7 + p_i * 13) % 30) - 15
                    p_y = y_center + oy
                    p_color = cls.hex_to_ass_color(color, alpha=0)
                    # Each particle: appear at p_x/p_y, scale up then fade out
                    p_start_sec = round(start_sec + p_delay_ms / 1000.0, 3)
                    p_start_str = cls.seconds_to_ass_time(p_start_sec)
                    p_end_str   = cls.seconds_to_ass_time(round(p_start_sec + 0.45, 3))
                    script_content.append(
                        f"Dialogue: 0,{p_start_str},{p_end_str},Main,,0,0,0,,"
                        f"{{\\pos({p_x},{p_y})\\c{p_color}"
                        f"\\fscx{scale}\\fscy{scale}"
                        f"\\t(0,200,\\fscx{scale + 20}\\fscy{scale + 20})"
                        f"\\fad(0,220)}}{glyph}"
                    )

            elif animation_style == 'BUBBLE_BOUNCE':
                # Elastic bounce entry + rising ○ bubble particles.
                # Bubbles spawn near the text, drift upward at different speeds,
                # and fade out — giving a light, airy, soapy feel.
                duration_ms = duration_cs * 10
                mid_ms = duration_ms // 2
                s_x = font_scale_x
                s_y = font_scale_y
                bubble_tag = (
                    f"{{\\move({x_center},{y_center + 22},{x_center},{y_center})"
                    f"\\fscx{int(s_x * 0.88)}\\fscy{int(s_y * 0.88)}"
                    f"\\t(0,400,\\fscx{s_x}\\fscy{s_y})"
                    f"\\t(400,{mid_ms},\\fscx{int(s_x * 1.04)}\\fscy{int(s_y * 1.04)})"
                    f"\\t({mid_ms},{duration_ms},\\fscx{s_x}\\fscy{s_y})"
                    f"\\fad(180,220)}}"
                )
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{bubble_tag}{raw_line}")

                # Bubble particles — ○ glyphs of varying sizes rising upward.
                # Each bubble has a unique x-offset, rise speed (via move y delta),
                # size, and delay. They stay alive for 0.7–1.1s then fade out.
                bubble_configs = [
                    # (x_offset, y_start_offset, y_rise, scale, delay_ms, lifetime_ms)
                    (-120,  20,  90, 38, 0,   900),
                    (  80,  18, 110, 28, 80,  800),
                    ( 150,  10,  75, 50, 160, 950),
                    ( -60,  25,  95, 22, 240, 750),
                    ( -185, 15, 120, 32, 100, 1000),
                    ( 195,  22,  85, 42, 200, 850),
                    (  30,  28, 100, 18, 320, 700),
                    ( -95,  12,  80, 36, 50,  900),
                ]
                b_color = cls.hex_to_ass_color(highlight_color, alpha=50)
                for b_i, (bx_off, by_off, y_rise, bscale, delay_ms, lifetime_ms) in enumerate(bubble_configs):
                    b_start_sec = round(start_sec + delay_ms / 1000.0, 3)
                    b_end_sec   = round(b_start_sec + lifetime_ms / 1000.0, 3)
                    # Cap bubble lifetime to line end
                    b_end_sec = min(b_end_sec, end_sec)
                    if b_end_sec <= b_start_sec:
                        continue
                    b_start_str = cls.seconds_to_ass_time(b_start_sec)
                    b_end_str   = cls.seconds_to_ass_time(b_end_sec)
                    b_x = x_center + bx_off + ((idx * 11 + b_i * 17) % 24) - 12
                    b_y_from = y_center + by_off
                    b_y_to   = y_center + by_off - y_rise
                    script_content.append(
                        f"Dialogue: 0,{b_start_str},{b_end_str},Main,,0,0,0,,"
                        f"{{\\move({b_x},{b_y_from},{b_x},{b_y_to})"
                        f"\\c{b_color}\\fscx{bscale}\\fscy{bscale}"
                        f"\\fad(80,300)}}○"
                    )

            elif animation_style == 'DREAMY_DRIFT':
                # Drift + ♪ ♫ floating music note particles.
                # Notes appear near the text and float upward, fading as they rise —
                # reinforcing the ethereal, musical atmosphere of the preset.
                duration_ms = duration_cs * 10
                exit_start_ms = max(300, duration_ms - 400)
                drift_tag = (
                    f"{{\\move({x_center},{y_center - 18},{x_center},{y_center + 22})"
                    f"\\blur6\\t(0,350,\\blur0)"
                    f"\\t({exit_start_ms},{duration_ms},\\blur4)"
                    f"\\fad(300,350)}}"
                )
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{drift_tag}{raw_line}")

                # Floating note particles — ♪ ♫ drift upward and dissolve.
                note_configs = [
                    # (x_offset, y_start_offset, y_rise, scale, delay_ms, lifetime_ms)
                    (-160,  10, 100, 55, 0,   1200),
                    ( 170,   8,  80, 45, 300, 1000),
                    ( -80,  15, 120, 35, 600, 1100),
                    ( 110,  12,  90, 50, 150, 1300),
                    (-210,   5, 110, 40, 450, 900),
                ]
                note_glyphs = ['♪', '♫', '♪', '♫', '♪']
                note_color = cls.hex_to_ass_color(highlight_color, alpha=60)
                for n_i, (nx_off, ny_off, y_rise, nscale, delay_ms, lifetime_ms) in enumerate(note_configs):
                    n_start_sec = round(start_sec + delay_ms / 1000.0, 3)
                    n_end_sec   = round(n_start_sec + lifetime_ms / 1000.0, 3)
                    n_end_sec   = min(n_end_sec, end_sec)
                    if n_end_sec <= n_start_sec:
                        continue
                    n_start_str = cls.seconds_to_ass_time(n_start_sec)
                    n_end_str   = cls.seconds_to_ass_time(n_end_sec)
                    n_x = x_center + nx_off + ((idx * 9 + n_i * 19) % 20) - 10
                    n_y_from = y_center + ny_off
                    n_y_to   = y_center + ny_off - y_rise
                    script_content.append(
                        f"Dialogue: 0,{n_start_str},{n_end_str},Main,,0,0,0,,"
                        f"{{\\move({n_x},{n_y_from},{n_x},{n_y_to})"
                        f"\\c{note_color}\\fscx{nscale}\\fscy{nscale}"
                        f"\\blur1\\fad(150,400)}}{note_glyphs[n_i]}"
                    )

            elif animation_style == 'NEON_GLOW':
                # Two-layer neon effect:
                # Layer 0 (bloom): a blurred copy of the whole line in the highlight
                #   color at 60% alpha — acts as the neon tube glow behind the text.
                #   Fades in/out with the line. blur5 gives a wide soft corona.
                # Layer 1 (wipe): the sharp karaoke wipe on top using \ko (outline
                #   karaoke) so the outline pulses as each word is highlighted,
                #   reinforcing the neon-on-dark-glass look.
                if words_list and len(words_list) > 0:
                    k_parts = []
                    for w in words_list:
                        w_text = w.get('word', '')
                        w_cs = max(5, int((float(w.get('end', float(w.get('start', start_sec)) + 0.3)) - float(w.get('start', start_sec))) * 100))
                        k_parts.append(f"{{\\ko{w_cs}}}{w_text}")
                    neon_line = " ".join(k_parts)
                else:
                    words = raw_line.split(' ')
                    total_chars = max(1, sum(len(w) for w in words))
                    neon_line = " ".join([f"{{\\ko{max(8, int(duration_cs * (len(w) / total_chars)))}}}{w}" for w in words])
                bloom_color = cls.hex_to_ass_color(highlight_color, alpha=100)
                # Bloom layer
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},NeonGlow,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center})\\blur5\\c{bloom_color}\\fad(120,120)}}{raw_line}"
                )
                # Sharp wipe layer on top
                script_content.append(
                    f"Dialogue: 1,{start_time_str},{end_time_str},NeonGlow,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center})\\blur0\\fad(80,80)}}{neon_line}"
                )

                # Electric spark particles — ✦ ✧ scatter around the text,
                # each appearing at a staggered time and fading out quickly.
                # They use the highlight color to match the neon tube glow.
                spark_glyphs   = ['✦', '✧', '✦', '✧', '✦', '✧', '✦', '✧']
                spark_offsets  = [
                    (-170, -22), ( 175, -18), (-100, -38), ( 105, -35),
                    (-195,  10), ( 198,  14), ( -55,  32), (  60,  30),
                ]
                spark_scales   = [35, 28, 22, 32, 25, 20, 30, 18]
                spark_color    = cls.hex_to_ass_color(highlight_color, alpha=20)
                for sp_i, (glyph, (sx_off, sy_off), sscale) in enumerate(zip(
                    spark_glyphs, spark_offsets, spark_scales
                )):
                    sp_delay_ms  = sp_i * 60 + (idx * 23 % 40)
                    sp_start_sec = round(start_sec + sp_delay_ms / 1000.0, 3)
                    sp_end_sec   = round(sp_start_sec + 0.35, 3)
                    sp_end_sec   = min(sp_end_sec, end_sec)
                    if sp_end_sec <= sp_start_sec:
                        continue
                    sp_x = x_center + sx_off
                    sp_y = y_center + sy_off
                    script_content.append(
                        f"Dialogue: 0,{cls.seconds_to_ass_time(sp_start_sec)},"
                        f"{cls.seconds_to_ass_time(sp_end_sec)},NeonGlow,,0,0,0,,"
                        f"{{\\pos({sp_x},{sp_y})\\c{spark_color}"
                        f"\\fscx{sscale}\\fscy{sscale}"
                        f"\\t(0,120,\\fscx{sscale + 15}\\fscy{sscale + 15})"
                        f"\\fad(40,180)}}{glyph}"
                    )

            elif animation_style == 'HANDWRITTEN_INK':
                # \kf character-fill reveal + micro ink-splatter dots.
                # Small · dots appear just ahead of the writing position,
                # simulating ink hitting the page before the stroke arrives.
                chars = list(raw_line)
                if not chars:
                    script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{raw_line}")
                else:
                    char_dur = max(3, int(duration_cs / len(chars)))
                    ink_line = "".join(f"{{\\kf{char_dur}}}{c}" for c in chars)
                    ink_tag = f"{{\\move({x_center},{y_center + 8},{x_center},{y_center})\\fad(0,200)}}"
                    script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{ink_tag}{ink_line}")

                    # Ink splatter dots — · appear at staggered positions near
                    # the start of the line and fade quickly (80ms lifetime).
                    # X positions spread outward from center left, matching the
                    # left-to-right writing direction of the kf reveal.
                    n_chars = len(chars)
                    splat_color = cls.hex_to_ass_color(highlight_color, alpha=80)
                    splat_offsets = [-160, -120, -80, -40, 0, 40, 80, 120, 160]
                    splat_y_jitter = [-8, 10, -5, 12, -10, 7, -12, 5, -7]
                    for sp_i, (sx_off, sy_jit) in enumerate(zip(splat_offsets, splat_y_jitter)):
                        # Stagger: each dot appears as the \kf wipe reaches its x position
                        sp_frac = (sp_i / len(splat_offsets))
                        sp_start_sec = round(start_sec + sp_frac * (end_sec - start_sec) * 0.85, 3)
                        sp_end_sec   = round(sp_start_sec + 0.12, 3)
                        sp_end_sec   = min(sp_end_sec, end_sec)
                        if sp_end_sec <= sp_start_sec:
                            continue
                        sp_x = x_center + sx_off + ((idx * 5 + sp_i * 11) % 16) - 8
                        sp_y = y_center + sy_jit
                        sp_scale = 20 + (sp_i % 3) * 8
                        script_content.append(
                            f"Dialogue: 0,{cls.seconds_to_ass_time(sp_start_sec)},"
                            f"{cls.seconds_to_ass_time(sp_end_sec)},Main,,0,0,0,,"
                            f"{{\\pos({sp_x},{sp_y})\\c{splat_color}"
                            f"\\fscx{sp_scale}\\fscy{sp_scale}\\fad(0,60)}}·"
                        )

            elif animation_style == 'RETRO_VHS':
                # Three-layer RGB chromatic aberration + scanline noise overlay.
                # Layers 0-1: red/cyan channel shift (as before).
                # Layer 2: main white text.
                # Scanline layer: ░ block glyphs at very low alpha across the
                # text height — simulate VHS tracking noise / interlace lines.
                duration_ms = duration_cs * 10
                red_color  = cls.hex_to_ass_color('#FF4444', alpha=140)
                cyan_color = cls.hex_to_ass_color('#44FFEE', alpha=150)
                # Red channel drifts right: x+3→x+7 over the line duration
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\move({x_center + 3},{y_center - 2},{x_center + 7},{y_center - 2})"
                    f"\\c{red_color}\\blur1\\fad(30,30)}}{raw_line}"
                )
                # Cyan channel: fixed offset left
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\pos({x_center - 3},{y_center + 2})\\c{cyan_color}\\blur1"
                    f"\\fad(30,30)}}{raw_line}"
                )
                # Main white layer on top
                script_content.append(
                    f"Dialogue: 1,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center})\\fad(50,50)}}{raw_line}"
                )

                # Scanline noise — horizontal ░ strips at varying y offsets and
                # very low alpha, flickering in/out at different times.
                # Each strip is a wide, short-lived block at one of 6 y positions.
                noise_color = cls.hex_to_ass_color('#FFFFFF', alpha=210)
                noise_rows = [
                    # (y_offset, x_offset, fscx, fscy, delay_ms, lifetime_ms)
                    ( -18, -80, 280, 18,  0,   180),
                    (   8,  60, 220, 14,  90,  160),
                    (  18, -40, 300, 16,  40,  200),
                    ( -10,  20, 180, 12, 130,  150),
                    (  -4, -60, 240, 20,  70,  170),
                    (  14,  30, 260, 14, 160,  140),
                ]
                for nr_i, (ny_off, nx_off, nfscx, nfscy, delay_ms, lifetime_ms) in enumerate(noise_rows):
                    nr_start_sec = round(start_sec + delay_ms / 1000.0, 3)
                    nr_end_sec   = round(nr_start_sec + lifetime_ms / 1000.0, 3)
                    nr_end_sec   = min(nr_end_sec, end_sec)
                    if nr_end_sec <= nr_start_sec:
                        continue
                    nr_x = x_center + nx_off
                    nr_y = y_center + ny_off
                    script_content.append(
                        f"Dialogue: 0,{cls.seconds_to_ass_time(nr_start_sec)},"
                        f"{cls.seconds_to_ass_time(nr_end_sec)},Main,,0,0,0,,"
                        f"{{\\pos({nr_x},{nr_y})\\c{noise_color}"
                        f"\\fscx{nfscx}\\fscy{nfscy}\\fad(0,60)}}░"
                    )

            elif animation_style == 'VINTAGE_COUNTRY':
                # Warm slow fade — line fades in from nothing over 400ms,
                # holds clean, then fades out slowly over 500ms. The slow dissolve
                # feels warm and unhurried. Uses the main style with amber highlight.
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center})\\fad(400,500)}}{raw_line}"
                )

            elif animation_style == 'ROLLING_3LINE':
                # Slide-based rolling display — lines physically move rather than
                # fading in place, matching how Spotify/Apple Music render lyrics.
                #
                # Transition window: first 180ms of each line's display period.
                # Previous line: slides from y_center → y_prev (moves up) during entry.
                # Current line: slides from y_next → y_center (arrives from below).
                # Next line: appears statically at y_next, dim.
                slide_ms = 180  # transition duration in ms

                # 1. Previous line — slides upward as new line arrives
                if idx > 0:
                    prev_item = lyrics_data[idx - 1]
                    if prev_item.get('line') and prev_item['line'] != '♪':
                        prev_text = prev_item['line']
                        if text_transform == 'uppercase': prev_text = prev_text.upper()
                        elif text_transform == 'lowercase': prev_text = prev_text.lower()
                        elif text_transform == 'capitalize': prev_text = prev_text.title()
                        script_content.append(
                            f"Dialogue: 0,{start_time_str},{end_time_str},RollingDim,,0,0,0,,"
                            f"{{\\move({x_center},{y_center},{x_center},{y_prev})"
                            f"\\fad(0,200)}}{prev_text}"
                        )

                # 2. Current line — slides up from y_next into y_center
                script_content.append(
                    f"Dialogue: 1,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\move({x_center},{y_next},{x_center},{y_center})"
                    f"\\fad(80,120)}}{raw_line}"
                )

                # 3. Next line — static at y_next, dim, no movement yet
                if idx + 1 < len(lyrics_data):
                    next_item = lyrics_data[idx + 1]
                    if next_item.get('line') and next_item['line'] != '♪':
                        next_text = next_item['line']
                        if text_transform == 'uppercase': next_text = next_text.upper()
                        elif text_transform == 'lowercase': next_text = next_text.lower()
                        elif text_transform == 'capitalize': next_text = next_text.title()
                        script_content.append(
                            f"Dialogue: 0,{start_time_str},{end_time_str},RollingDim,,0,0,0,,"
                            f"{{\\pos({x_center},{y_next})\\fad(200,100)}}{next_text}"
                        )

            elif animation_style == 'CYBER_NEON':
                # unchanged — already has blur + karaoke wipe on NeonGlow style
                words = raw_line.split(' ')
                total_chars = max(1, sum(len(w) for w in words))
                neon_line = " ".join([f"{{\\k{max(8, int(duration_cs * (len(w)/total_chars)))}}}{w}" for w in words])
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},NeonGlow,,0,0,0,,{{\\blur2\\fad(120,120)}}{neon_line}")

            elif animation_style == 'CINEMATIC':
                # Slow-burn reveal: entry blur 2 → 0 over 200ms + imperceptible
                # upward float (8px over full duration) — how film subtitles move.
                # A second dimmed shadow layer sits 2px below for depth.
                duration_ms = duration_cs * 10
                shadow_color = cls.hex_to_ass_color('#000000', alpha=160)
                script_content.append(
                    f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\pos({x_center},{y_center + 2})\\c{shadow_color}\\blur2"
                    f"\\fad(280,280)}}{raw_line}"
                )
                script_content.append(
                    f"Dialogue: 1,{start_time_str},{end_time_str},Main,,0,0,0,,"
                    f"{{\\move({x_center},{y_center + 4},{x_center},{y_center - 4})"
                    f"\\blur2\\t(0,200,\\blur0)\\fad(280,280)}}{raw_line}"
                )

            elif animation_style == 'BOUNCE_IN':
                # Entry: scale 50%→108%→100% spring (overshoot + settle).
                # Exit: scale down to 60% + fade — matches the entry energy.
                # Fixed \pos so position doesn't drift across renderers.
                duration_ms = duration_cs * 10
                exit_start_ms = max(200, duration_ms - 180)
                s_x = font_scale_x
                s_y = font_scale_y
                bounce_tag = (
                    f"{{\\pos({x_center},{y_center})"
                    f"\\fscx{int(s_x * 0.5)}\\fscy{int(s_y * 0.5)}"
                    f"\\t(0,180,\\fscx{int(s_x * 1.08)}\\fscy{int(s_y * 1.08)})"
                    f"\\t(180,280,\\fscx{s_x}\\fscy{s_y})"
                    f"\\t({exit_start_ms},{duration_ms},\\fscx{int(s_x * 0.6)}\\fscy{int(s_y * 0.6)}\\alpha&HFF&)"
                    f"\\fad(0,0)}}"
                )
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{bounce_tag}{raw_line}")

            elif animation_style == 'TYPEWRITER':
                # True character-by-character reveal using per-char Dialogue events.
                # Each character gets its own event starting at its reveal time,
                # so characters literally appear from nothing rather than color-wiping.
                # Previously used \k which does a color wipe — not a real typewriter.
                chars = list(raw_line)
                if not chars:
                    script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{raw_line}")
                else:
                    n = len(chars)
                    char_slot_sec = (end_sec - start_sec) / n
                    # Build incrementally: each event shows all revealed chars so far
                    for c_i in range(n):
                        c_start_sec = round(start_sec + c_i * char_slot_sec, 3)
                        c_start_str = cls.seconds_to_ass_time(c_start_sec)
                        revealed = "".join(chars[:c_i + 1])
                        script_content.append(
                            f"Dialogue: {c_i},{c_start_str},{end_time_str},Main,,0,0,0,,"
                            f"{{\\pos({x_center},{y_center})\\fad(0,120)}}{revealed}"
                        )

            elif animation_style == 'WAVE_PULSE':
                # Bug fix: \t uses milliseconds, not centiseconds.
                # Grow to 105% over first half, shrink back over second half.
                # Added \pos and a colour shift on the peak for extra visual punch.
                duration_ms = duration_cs * 10
                mid_ms = duration_ms // 2
                s_x_max = int(font_scale_x * 1.06)
                s_y_max = int(font_scale_y * 1.06)
                peak_color = cls.hex_to_ass_color(highlight_color, alpha=0)
                pulse_tag = (
                    f"{{\\pos({x_center},{y_center})"
                    f"\\t(0,{mid_ms},\\fscx{s_x_max}\\fscy{s_y_max}\\c{peak_color})"
                    f"\\t({mid_ms},{duration_ms},\\fscx{font_scale_x}\\fscy{font_scale_y})"
                    f"\\fad(150,150)}}"
                )
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{pulse_tag}{raw_line}")

            elif animation_style == 'SLIDE_UP':
                # Move from slightly below to center
                y_start = y_center + 60
                move_tag = f"{{\\move({x_center},{y_start},{x_center},{y_center})\\fad(200,200)}}"
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{move_tag}{raw_line}")

            else:
                script_content.append(f"Dialogue: 0,{start_time_str},{end_time_str},Main,,0,0,0,,{raw_line}")

        os.makedirs(os.path.dirname(os.path.abspath(output_ass_path)), exist_ok=True)
        with open(output_ass_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(script_content))

        return output_ass_path

    @classmethod
    def generate_ambient_background_frame(
        cls,
        background_image_path,
        width,
        height,
        output_frame_path,
        cover_layout='AMBIENT',
        cover_size=1.0,
        cover_blur=8.0,
        cover_opacity=1.0,
        cover_offset=0.0,
        cover_brightness=1.0,
        cover_contrast=1.0,
        cover_saturation=1.0,
        cover_vignette=0.0
    ):
        """
        Creates a high-resolution ambient background frame with smooth Gaussian blur,
        dark vignette enhancement, and either a centered cover or a full-bleed cover.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_frame_path)), exist_ok=True)

        if background_image_path and os.path.exists(background_image_path):
            img = Image.open(background_image_path).convert('RGB')

            if cover_layout == 'FULL':
                # Full cover background with the same effect stack as the preview.
                img_ratio = img.width / max(img.height, 1)
                canvas_ratio = width / max(height, 1)
                target_w = int(width * min(max(cover_size, 0.2), 1.8))
                target_h = int(height * min(max(cover_size, 0.2), 1.8))

                if img_ratio > canvas_ratio:
                    new_h = int(target_h)
                    new_w = int(target_h * img_ratio)
                    left = max((width - new_w) // 2 + int(cover_offset), 0)
                    top = max((height - new_h) // 2, 0)
                    bg = Image.new('RGB', (width, height), color=(12, 12, 18))
                    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    bg.paste(resized, (left, top))
                else:
                    new_w = int(target_w)
                    new_h = int(target_w / img_ratio)
                    left = max((width - new_w) // 2 + int(cover_offset), 0)
                    top = max((height - new_h) // 2, 0)
                    bg = Image.new('RGB', (width, height), color=(12, 12, 18))
                    resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    bg.paste(resized, (left, top))

                if cover_blur > 0:
                    bg = bg.filter(ImageFilter.GaussianBlur(radius=float(cover_blur)))

                bg = ImageEnhance.Brightness(bg).enhance(max(cover_brightness, 0.1))
                bg = ImageEnhance.Contrast(bg).enhance(max(cover_contrast, 0.1))
                bg = ImageEnhance.Color(bg).enhance(max(cover_saturation, 0.0))

                if cover_opacity < 1.0:
                    bg = Image.blend(Image.new('RGB', bg.size, (12, 12, 18)), bg, float(max(min(cover_opacity, 1.0), 0.0)))

                if cover_vignette > 0:
                    vignette = Image.new('RGBA', bg.size, (0, 0, 0, 0))
                    draw = ImageDraw.Draw(vignette)
                    alpha = int(255 * min(max(cover_vignette, 0.0), 0.7))
                    draw.rectangle((0, 0, width, height), fill=(0, 0, 0, alpha))
                    bg = Image.alpha_composite(bg.convert('RGBA'), vignette).convert('RGB')
            else:
                # 1. Ambient blurred background
                bg = img.resize((width, height), Image.Resampling.LANCZOS)
                bg = bg.filter(ImageFilter.GaussianBlur(radius=30))
                enhancer = ImageEnhance.Brightness(bg)
                bg = enhancer.enhance(0.35)

                # 2. Centered album artwork with rounded corner effect & shadow
                target_art_size = int(min(width, height) * 0.42)
                art_thumb = img.resize((target_art_size, target_art_size), Image.Resampling.LANCZOS)

                pos_x = (width - target_art_size) // 2
                pos_y = int((height - target_art_size) * 0.30) if height > width else int((height - target_art_size) * 0.25)
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
        audio_path=None,
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
        cover_layout='AMBIENT',
        cover_size=1.0,
        cover_blur=8.0,
        cover_opacity=1.0,
        cover_offset=0.0,
        cover_brightness=1.0,
        cover_contrast=1.0,
        cover_saturation=1.0,
        cover_vignette=0.0,
        font_weight='bold',
        font_italic=False,
        letter_spacing=0.0,
        line_height=1.4,
        text_transform='none',
        text_stroke_width=2.5,
        text_shadow_depth=2.0,
        font_scale_x=100,
        font_scale_y=100,
        bg_opacity=0,
        title='Lyric Video',
        artist='',
        loop_video=True,
        project_id=None
    ):
        """
        Renders complete 1080p synchronized lyric video using local FFmpeg and ASS subtitle engine.
        Supports both:
        1. Source Video File (overlays lyrics onto existing video, preserving or replacing audio)
        2. Audio File + Cover Artwork / Ambient Dark Canvas
        """
        ffmpeg = cls.get_ffmpeg_binary()
        output_video_path = os.path.abspath(str(output_video_path))
        os.makedirs(os.path.dirname(output_video_path), exist_ok=True)

        if project_id:
            RenderProcessTracker.set_progress('lyrics', project_id, 10, "Inspecting media and preparing workspace...")
            if RenderProcessTracker.is_cancelled('lyrics', project_id):
                raise RuntimeError("Rendering cancelled by user.")

        # Validate input paths
        has_audio = bool(audio_path and os.path.exists(str(audio_path)))
        has_video = bool(background_video_path and os.path.exists(str(background_video_path)))

        if not has_audio and not has_video:
            raise FileNotFoundError("Neither a valid audio file nor a source video file was provided.")

        if has_audio:
            audio_path = os.path.abspath(str(audio_path))
            duration = cls.inspect_media_duration(audio_path)
        else:
            bg_vid = os.path.abspath(str(background_video_path))
            duration = cls.inspect_media_duration(bg_vid)

        # Ensure duration covers the entire lyrics timeline if looping enabled or audio present
        if lyrics_data:
            max_lyric_end = max([float(item.get('end', 0.0)) for item in lyrics_data if isinstance(item, dict) and 'end' in item] or [0.0])
            if max_lyric_end > duration and (loop_video or has_audio):
                duration = round(max_lyric_end, 2)

        if duration <= 0:
            duration = 60.0

        is_vertical = (aspect_ratio == '9:16')
        width = 1080 if is_vertical else 1920
        height = 1920 if is_vertical else 1080

        # Create temporary working directory for subtitle and frame assets
        temp_dir = os.path.join(os.path.dirname(output_video_path), f"temp_lyrics_{os.getpid()}")
        os.makedirs(temp_dir, exist_ok=True)

        try:
            if project_id:
                RenderProcessTracker.set_progress('lyrics', project_id, 25, "Generating synchronized ASS subtitle styling...")
                if RenderProcessTracker.is_cancelled('lyrics', project_id):
                    raise RuntimeError("Rendering cancelled by user.")

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
                position_mode=position_mode,
                font_weight=font_weight,
                font_italic=font_italic,
                letter_spacing=letter_spacing,
                line_height=line_height,
                text_transform=text_transform,
                text_stroke_width=text_stroke_width,
                text_shadow_depth=text_shadow_depth,
                font_scale_x=font_scale_x,
                font_scale_y=font_scale_y,
                bg_opacity=bg_opacity
            )

            # Escape subtitle path for FFmpeg filter on Windows
            escaped_ass_path = ass_path.replace('\\', '/').replace(':', '\\:')

            if project_id:
                RenderProcessTracker.set_progress('lyrics', project_id, 45, "Preparing visual composition & video layout...")
                if RenderProcessTracker.is_cancelled('lyrics', project_id):
                    raise RuntimeError("Rendering cancelled by user.")

            # 2. Build FFmpeg command depending on source media
            if has_video:
                bg_vid = os.path.abspath(str(background_video_path))
                vf_filter = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"ass='{escaped_ass_path}'"
                )

                stream_loop_args = ['-stream_loop', '-1'] if loop_video else []

                if has_audio:
                    # Video source + custom audio track replacement
                    cmd = [
                        ffmpeg, '-y'
                    ] + stream_loop_args + [
                        '-i', bg_vid,
                        '-i', audio_path,
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        '-vf', vf_filter,
                        '-c:v', 'libx264',
                        '-preset', 'veryfast',
                        '-threads', '0',
                        '-crf', '20',
                        '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-t', str(duration),
                        '-movflags', '+faststart',
                        output_video_path
                    ]
                else:
                    # Source video file alone (overlays lyrics onto video, preserves video soundtrack)
                    cmd = [
                        ffmpeg, '-y'
                    ] + stream_loop_args + [
                        '-i', bg_vid,
                        '-vf', vf_filter,
                        '-map', '0:v:0',
                        '-map', '0:a?',
                        '-c:v', 'libx264',
                        '-preset', 'veryfast',
                        '-threads', '0',
                        '-crf', '20',
                        '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac',
                        '-b:a', '192k',
                        '-t', str(duration),
                        '-movflags', '+faststart',
                        output_video_path
                    ]
            else:
                # Prepare background image frame + audio
                frame_path = os.path.join(temp_dir, "bg_frame.jpg")
                cls.generate_ambient_background_frame(
                    background_image_path=background_image_path,
                    width=width,
                    height=height,
                    output_frame_path=frame_path,
                    cover_layout=cover_layout,
                    cover_size=cover_size,
                    cover_blur=cover_blur,
                    cover_opacity=cover_opacity,
                    cover_offset=cover_offset,
                    cover_brightness=cover_brightness,
                    cover_contrast=cover_contrast,
                    cover_saturation=cover_saturation,
                    cover_vignette=cover_vignette
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
                    '-tune', 'stillimage',
                    '-preset', 'veryfast',
                    '-threads', '0',
                    '-crf', '20',
                    '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    '-shortest',
                    '-t', str(duration),
                    '-movflags', '+faststart',
                    output_video_path
                ]

            if project_id:
                RenderProcessTracker.set_progress('lyrics', project_id, 55, "Encoding 1080p synchronized video frames with FFmpeg...")
                if RenderProcessTracker.is_cancelled('lyrics', project_id):
                    raise RuntimeError("Rendering cancelled by user.")

            # Execute rendering command with live cancellation tracking
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors='ignore',
                **cls.get_subprocess_kwargs()
            )

            if project_id:
                RenderProcessTracker.register('lyrics', project_id, proc)

            stdout, stderr = "", ""
            try:
                while True:
                    try:
                        stdout, stderr = proc.communicate(timeout=0.5)
                        break
                    except subprocess.TimeoutExpired:
                        if project_id and RenderProcessTracker.is_cancelled('lyrics', project_id):
                            proc.kill()
                            try:
                                proc.communicate()
                            except Exception:
                                pass
                            raise RuntimeError("Rendering cancelled by user.")
            finally:
                if project_id:
                    RenderProcessTracker.unregister('lyrics', project_id, proc)

            if proc.returncode != 0 or not os.path.exists(output_video_path) or os.path.getsize(output_video_path) == 0:
                if project_id and RenderProcessTracker.is_cancelled('lyrics', project_id):
                    raise RuntimeError("Rendering cancelled by user.")
                raise RuntimeError(f"FFmpeg lyric video render failed: {stderr[-1000:]}")

            if project_id:
                RenderProcessTracker.set_progress('lyrics', project_id, 95, "Finalizing MP4 video streams & metadata...")

            return {
                'success': True,
                'output_video': output_video_path,
                'duration': duration
            }

        finally:
            if project_id and not RenderProcessTracker.is_cancelled('lyrics', project_id):
                RenderProcessTracker.set_progress('lyrics', project_id, 100, "Rendering complete!")

            # Clean up temporary working directory
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass
            except Exception:
                pass
