import json
import logging
import urllib.parse
import requests
from django.conf import settings
from django.utils import timezone
from apps.artists.models import YouTubeChannel
from apps.publishing.models import YouTubeOAuthAccount

logger = logging.getLogger(__name__)

class YouTubeOAuthService:
    """
    Handles Google OAuth 2.0 Web Server authorization flow and token management.
    """
    AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URI = "https://oauth2.googleapis.com/token"
    REVOKE_URI = "https://oauth2.googleapis.com/revoke"
    CHANNELS_API = "https://www.googleapis.com/youtube/v3/channels"

    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/youtube.force-ssl",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/userinfo.email"
    ]

    @classmethod
    def get_client_credentials(cls):
        """Returns client_id and client_secret from Django settings or environment."""
        client_id = getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '')
        client_secret = getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '')
        return client_id.strip(), client_secret.strip()

    @classmethod
    def is_configured(cls):
        client_id, client_secret = cls.get_client_credentials()
        return bool(client_id and client_secret)

    @classmethod
    def get_authorization_url(cls, redirect_uri, state=None):
        """
        Builds the Google OAuth 2.0 authorization URL.
        Requests offline access and forces consent to guarantee receiving a refresh_token.
        """
        client_id, _ = cls.get_client_credentials()
        if not client_id:
            raise ValueError("Google OAuth Client ID is not configured in settings or .env.")

        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(cls.SCOPES),
            'access_type': 'offline',
            'prompt': 'consent',
            'include_granted_scopes': 'true'
        }
        if state:
            params['state'] = state

        return f"{cls.AUTH_URI}?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_tokens(cls, code, redirect_uri):
        """
        Exchanges the authorization code for access and refresh tokens.
        """
        client_id, client_secret = cls.get_client_credentials()
        if not client_id or not client_secret:
            raise ValueError("Google OAuth credentials missing.")

        payload = {
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }

        response = requests.post(cls.TOKEN_URI, data=payload, timeout=15)
        if response.status_code != 200:
            error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            err_msg = error_data.get('error_description') or error_data.get('error') or response.text
            raise RuntimeError(f"Failed to exchange authorization code: {err_msg}")

        token_data = response.json()
        token_data['client_id'] = client_id
        token_data['client_secret'] = client_secret
        token_data['token_uri'] = cls.TOKEN_URI
        token_data['scopes'] = cls.SCOPES
        return token_data

    @classmethod
    def fetch_channel_profile(cls, access_token):
        """
        Fetches channel details of the currently authenticated user from YouTube API.
        """
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {
            'part': 'snippet,statistics,contentDetails',
            'mine': 'true'
        }

        response = requests.get(cls.CHANNELS_API, headers=headers, params=params, timeout=15)
        if response.status_code != 200:
            raise RuntimeError(f"Could not fetch YouTube channel details: {response.text}")

        data = response.json()
        items = data.get('items', [])
        if not items:
            raise RuntimeError("No YouTube channel found for the authenticated Google account.")

        ch = items[0]
        snippet = ch.get('snippet', {})
        stats = ch.get('statistics', {})

        thumbnail_url = (
            snippet.get('thumbnails', {}).get('high', {}).get('url') or
            snippet.get('thumbnails', {}).get('medium', {}).get('url') or
            snippet.get('thumbnails', {}).get('default', {}).get('url') or
            ''
        )

        return {
            'channel_id': ch.get('id', ''),
            'channel_title': snippet.get('title', 'YouTube Channel'),
            'channel_custom_url': snippet.get('customUrl', ''),
            'thumbnail_url': thumbnail_url,
            'subscriber_count': int(stats.get('subscriberCount', 0)),
            'video_count': int(stats.get('videoCount', 0)),
        }

    @classmethod
    def register_or_update_account(cls, token_data):
        """
        Takes raw token data, queries YouTube for channel info, and creates or updates
        the YouTubeOAuthAccount record. Automatically links to existing YouTubeChannel if matched.
        """
        access_token = token_data.get('access_token')
        channel_info = cls.fetch_channel_profile(access_token)
        channel_id = channel_info['channel_id']

        # Check for matching channel in artist database
        linked_channel = YouTubeChannel.objects.filter(channel_id=channel_id).first()

        # If refresh token not returned in this exchange (e.g. re-auth), keep previous refresh token
        account = YouTubeOAuthAccount.objects.filter(channel_id=channel_id).first()
        if account and not token_data.get('refresh_token') and account.token_json.get('refresh_token'):
            token_data['refresh_token'] = account.token_json['refresh_token']

        if account:
            account.channel_title = channel_info['channel_title']
            account.channel_custom_url = channel_info['channel_custom_url']
            account.thumbnail_url = channel_info['thumbnail_url']
            account.subscriber_count = channel_info['subscriber_count']
            account.video_count = channel_info['video_count']
            account.token_json = token_data
            account.is_active = True
            if linked_channel:
                account.linked_channel = linked_channel
            account.save()
            logger.info(f"Updated YouTube OAuth account: {account.channel_title} ({account.channel_id})")
        else:
            is_first = not YouTubeOAuthAccount.objects.exists()
            account = YouTubeOAuthAccount.objects.create(
                channel_id=channel_id,
                channel_title=channel_info['channel_title'],
                channel_custom_url=channel_info['channel_custom_url'],
                thumbnail_url=channel_info['thumbnail_url'],
                subscriber_count=channel_info['subscriber_count'],
                video_count=channel_info['video_count'],
                token_json=token_data,
                is_active=True,
                is_default=is_first,
                linked_channel=linked_channel
            )
            logger.info(f"Registered new YouTube OAuth account: {account.channel_title} ({account.channel_id})")

        return account

    @classmethod
    def disconnect_account(cls, account_id):
        """
        Revokes OAuth token and removes or deactivates the account record.
        """
        account = YouTubeOAuthAccount.objects.get(pk=account_id)
        refresh_token = account.token_json.get('refresh_token') or account.token_json.get('access_token')
        if refresh_token:
            try:
                requests.post(cls.REVOKE_URI, params={'token': refresh_token}, timeout=5)
            except Exception as e:
                logger.warning(f"Could not revoke token on Google servers: {e}")

        account_name = account.channel_title
        account.delete()
        
        # If deleted was default, make another one default
        remaining = YouTubeOAuthAccount.objects.first()
        if remaining and not YouTubeOAuthAccount.objects.filter(is_default=True).exists():
            remaining.is_default = True
            remaining.save()

        return account_name
