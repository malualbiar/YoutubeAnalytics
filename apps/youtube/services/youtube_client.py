import os
import re
import logging
import requests
from django.conf import settings
from apps.youtube.models import YouTubeApiUsage

logger = logging.getLogger(__name__)

class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors"""
    pass

class YouTubeClient:
    """
    Dedicated YouTube Data API v3 client with quota tracking,
    batching, and robust error handling.
    """
    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key=None):
        self.api_key = api_key or getattr(settings, 'YOUTUBE_API_KEY', '') or os.getenv('YOUTUBE_API_KEY', '')
        if not self.api_key:
            logger.warning("YouTube API Key is not configured. Real API calls will fail.")

    def _make_request(self, endpoint, params, quota_cost=1):
        """
        Execute request to YouTube API v3 and track quota usage.
        """
        if not self.api_key:
            raise YouTubeAPIError("YouTube API key is missing. Please set YOUTUBE_API_KEY in .env or settings.")

        url = f"{self.BASE_URL}/{endpoint}"
        request_params = {'key': self.api_key, **params}

        try:
            response = requests.get(url, params=request_params, timeout=15)
            # Record quota consumption
            try:
                YouTubeApiUsage.record_usage(units=quota_cost)
            except Exception as e:
                logger.warning(f"Could not record API quota usage: {e}")

            if response.status_code == 200:
                return response.json()

            # Handle errors gracefully
            error_data = response.json().get('error', {})
            errors = error_data.get('errors', [])
            reason = errors[0].get('reason', '') if errors else ''
            message = error_data.get('message', response.text)

            if response.status_code == 403:
                if 'quotaExceeded' in reason or 'quota' in message.lower():
                    raise YouTubeAPIError("YouTube API quota exceeded for today (10,000 units limit reached).")
                raise YouTubeAPIError(f"YouTube API permission denied: {message}")
            elif response.status_code == 404:
                raise YouTubeAPIError(f"YouTube resource not found: {message}")
            elif response.status_code == 400:
                raise YouTubeAPIError(f"YouTube API bad request: {message}")
            else:
                raise YouTubeAPIError(f"YouTube API error ({response.status_code}): {message}")

        except requests.exceptions.RequestException as e:
            raise YouTubeAPIError(f"Network error connecting to YouTube API: {str(e)}")

    def get_channel_by_id(self, channel_id):
        """Fetch channel snippet, statistics, and contentDetails by channel ID (Cost: 1 unit)"""
        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': channel_id
        }
        data = self._make_request('channels', params, quota_cost=1)
        items = data.get('items', [])
        return items[0] if items else None

    def get_channel_by_handle_or_for_username(self, handle_or_username):
        """
        Fetch channel by handle (e.g. @artist) or forUsername (Cost: 1 unit)
        """
        clean_name = handle_or_username.lstrip('@')
        # Try forHandle first (Data API v3 support)
        try:
            params = {
                'part': 'snippet,statistics,contentDetails',
                'forHandle': clean_name
            }
            data = self._make_request('channels', params, quota_cost=1)
            items = data.get('items', [])
            if items:
                return items[0]
        except Exception:
            pass

        # Try forUsername fallback
        try:
            params = {
                'part': 'snippet,statistics,contentDetails',
                'forUsername': clean_name
            }
            data = self._make_request('channels', params, quota_cost=1)
            items = data.get('items', [])
            if items:
                return items[0]
        except Exception:
            pass

        # Search fallback (Cost: 100 units - use sparingly)
        try:
            params = {
                'part': 'snippet',
                'q': handle_or_username,
                'type': 'channel',
                'maxResults': 1
            }
            search_data = self._make_request('search', params, quota_cost=100)
            items = search_data.get('items', [])
            if items:
                ch_id = items[0]['id']['channelId']
                return self.get_channel_by_id(ch_id)
        except Exception as e:
            logger.error(f"Error searching channel by name: {e}")

        return None

    def get_playlist_items(self, playlist_id, max_results=50, page_token=None):
        """Fetch video IDs from an uploads playlist (Cost: 1 unit)"""
        params = {
            'part': 'snippet,contentDetails',
            'playlistId': playlist_id,
            'maxResults': min(max_results, 50)
        }
        if page_token:
            params['pageToken'] = page_token

        return self._make_request('playlistItems', params, quota_cost=1)

    def get_videos_batch(self, video_ids):
        """
        Fetch statistics, snippet, and contentDetails for up to 50 videos in one call (Cost: 1 unit)
        """
        if not video_ids:
            return []
        
        # Take up to 50 video IDs
        ids_str = ','.join(video_ids[:50])
        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': ids_str
        }
        data = self._make_request('videos', params, quota_cost=1)
        return data.get('items', [])
