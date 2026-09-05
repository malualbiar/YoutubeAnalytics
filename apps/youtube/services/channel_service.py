import re
import logging
from urllib.parse import urlparse
from .youtube_client import YouTubeClient, YouTubeAPIError

logger = logging.getLogger(__name__)

class ChannelService:
    def __init__(self, client=None):
        self.client = client or YouTubeClient()

    @staticmethod
    def extract_identifier(input_text):
        """
        Extract channel ID, handle (@username), or username from raw text or full URL.
        Examples:
        - 'https://www.youtube.com/@TheWeeknd' -> ('handle', '@TheWeeknd')
        - 'https://www.youtube.com/channel/UCxxxxxxxxxxxx' -> ('id', 'UCxxxxxxxxxxxx')
        - 'https://www.youtube.com/c/ArtistName' -> ('custom', 'ArtistName')
        - 'https://www.youtube.com/user/ArtistName' -> ('username', 'ArtistName')
        - '@TheWeeknd' -> ('handle', '@TheWeeknd')
        - 'UCxxxxxxxxxxxxxxxxxxxx' -> ('id', 'UCxxxxxxxxxxxxxxxxxxxx')
        """
        text = input_text.strip()
        if not text:
            return None, None

        # Check raw channel ID (starts with UC and is ~24 chars)
        if re.match(r'^UC[a-zA-Z0-9_-]{22}$', text):
            return 'id', text

        # Check handle directly (@username)
        if text.startswith('@'):
            return 'handle', text

        # Parse as URL
        if 'youtube.com' in text or 'youtu.be' in text:
            parsed = urlparse(text)
            path = parsed.path.strip('/')
            parts = path.split('/')

            if len(parts) >= 2 and parts[0] == 'channel':
                return 'id', parts[1]
            elif len(parts) >= 2 and parts[0] in ['c', 'user']:
                return 'username', parts[1]
            elif len(parts) >= 1 and parts[0].startswith('@'):
                return 'handle', parts[0]
            elif len(parts) == 1 and parts[0]:
                return 'custom', parts[0]

        # Default fallback: treat as handle or name
        return 'handle', f"@{text}" if not text.startswith('@') else text

    def resolve_channel(self, identifier_or_url):
        """
        Resolve a YouTube channel from URL, handle, or ID and return structured metadata.
        """
        kind, value = self.extract_identifier(identifier_or_url)
        if not kind or not value:
            raise YouTubeAPIError("Invalid YouTube URL, handle, or Channel ID provided.")

        raw_channel = None
        if kind == 'id':
            raw_channel = self.client.get_channel_by_id(value)
        else:
            raw_channel = self.client.get_channel_by_handle_or_for_username(value)

        if not raw_channel:
            raise YouTubeAPIError(f"Could not find a YouTube channel matching '{identifier_or_url}'. Please verify the handle or ID.")

        snippet = raw_channel.get('snippet', {})
        statistics = raw_channel.get('statistics', {})
        content_details = raw_channel.get('contentDetails', {})
        related_playlists = content_details.get('relatedPlaylists', {})

        thumbnails = snippet.get('thumbnails', {})
        best_thumbnail = (
            thumbnails.get('high', {}).get('url') or
            thumbnails.get('medium', {}).get('url') or
            thumbnails.get('default', {}).get('url') or
            ''
        )

        custom_url = snippet.get('customUrl', '')
        channel_url = f"https://www.youtube.com/{custom_url}" if custom_url else f"https://www.youtube.com/channel/{raw_channel.get('id')}"

        return {
            'channel_id': raw_channel.get('id'),
            'channel_name': snippet.get('title', 'Unknown Channel'),
            'channel_url': channel_url,
            'thumbnail_url': best_thumbnail,
            'description': snippet.get('description', ''),
            'subscriber_count': int(statistics.get('subscriberCount', 0)) if not statistics.get('hiddenSubscriberCount', False) else 0,
            'total_views': int(statistics.get('viewCount', 0)),
            'video_count': int(statistics.get('videoCount', 0)),
            'uploads_playlist_id': related_playlists.get('uploads', ''),
            'raw_data': raw_channel
        }
