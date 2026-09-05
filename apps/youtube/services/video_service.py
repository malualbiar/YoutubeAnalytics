import re
import logging
from datetime import datetime
from django.utils import timezone
from .youtube_client import YouTubeClient, YouTubeAPIError

logger = logging.getLogger(__name__)

class VideoService:
    def __init__(self, client=None):
        self.client = client or YouTubeClient()

    @staticmethod
    def parse_iso8601_duration(duration_str):
        """
        Parse ISO 8601 duration (e.g. 'PT3M45S', 'PT1H2M30S', 'PT45S')
        Returns (formatted_string, total_seconds)
        """
        if not duration_str or duration_str == 'P0D':
            return '0:00', 0

        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        if not match:
            return '0:00', 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = (hours * 3600) + (minutes * 60) + seconds

        if hours > 0:
            formatted = f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            formatted = f"{minutes}:{seconds:02d}"

        return formatted, total_seconds

    def fetch_channel_videos(self, uploads_playlist_id, max_videos=100):
        """
        Fetch all recent video IDs from the uploads playlist (up to max_videos)
        and then batch fetch their full details and statistics in chunks of 50.
        """
        if not uploads_playlist_id:
            return []

        video_ids = []
        page_token = None

        while len(video_ids) < max_videos:
            fetch_count = min(50, max_videos - len(video_ids))
            data = self.client.get_playlist_items(uploads_playlist_id, max_results=fetch_count, page_token=page_token)
            items = data.get('items', [])
            if not items:
                break

            for item in items:
                v_id = item.get('contentDetails', {}).get('videoId')
                if v_id and v_id not in video_ids:
                    video_ids.append(v_id)

            page_token = data.get('nextPageToken')
            if not page_token:
                break

        # Batch fetch video statistics in chunks of 50
        detailed_videos = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i:i + 50]
            items = self.client.get_videos_batch(chunk)
            for item in items:
                detailed_videos.append(self._parse_video_item(item))

        return detailed_videos

    def _parse_video_item(self, item):
        """Parse raw YouTube video item into clean dict"""
        snippet = item.get('snippet', {})
        stats = item.get('statistics', {})
        content_details = item.get('contentDetails', {})

        video_id = item.get('id')
        published_str = snippet.get('publishedAt')
        published_at = timezone.now()
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
            except Exception:
                published_at = timezone.now()

        thumbnails = snippet.get('thumbnails', {})
        best_thumbnail = (
            thumbnails.get('maxres', {}).get('url') or
            thumbnails.get('high', {}).get('url') or
            thumbnails.get('medium', {}).get('url') or
            thumbnails.get('default', {}).get('url') or
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        )

        duration_raw = content_details.get('duration', '')
        duration_fmt, duration_sec = self.parse_iso8601_duration(duration_raw)

        return {
            'youtube_video_id': video_id,
            'title': snippet.get('title', 'Untitled Video'),
            'description': snippet.get('description', ''),
            'thumbnail_url': best_thumbnail,
            'published_at': published_at,
            'duration': duration_fmt,
            'duration_seconds': duration_sec,
            'video_url': f"https://www.youtube.com/watch?v={video_id}",
            'current_views': int(stats.get('viewCount', 0)),
            'current_likes': int(stats.get('likeCount', 0)),
            'current_comments': int(stats.get('commentCount', 0)),
        }
