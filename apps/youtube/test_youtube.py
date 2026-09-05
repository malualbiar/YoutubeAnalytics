from django.test import TestCase
from apps.youtube.services.channel_service import ChannelService
from apps.youtube.services.video_service import VideoService

class YouTubeServiceTests(TestCase):
    def test_extract_identifier(self):
        service = ChannelService()
        
        # Test handle URL
        kind, val = service.extract_identifier('https://www.youtube.com/@TheWeeknd')
        self.assertEqual(kind, 'handle')
        self.assertEqual(val, '@TheWeeknd')

        # Test raw handle
        kind, val = service.extract_identifier('@DuaLipa')
        self.assertEqual(kind, 'handle')
        self.assertEqual(val, '@DuaLipa')

        # Test channel ID URL
        kind, val = service.extract_identifier('https://www.youtube.com/channel/UC1234567890123456789012')
        self.assertEqual(kind, 'id')
        self.assertEqual(val, 'UC1234567890123456789012')

        # Test raw channel ID
        kind, val = service.extract_identifier('UC1234567890123456789012')
        self.assertEqual(kind, 'id')
        self.assertEqual(val, 'UC1234567890123456789012')

    def test_parse_iso8601_duration(self):
        vservice = VideoService()

        # PT3M45S -> 3:45, 225s
        fmt, sec = vservice.parse_iso8601_duration('PT3M45S')
        self.assertEqual(fmt, '3:45')
        self.assertEqual(sec, 225)

        # PT1H2M30S -> 1:02:30, 3750s
        fmt, sec = vservice.parse_iso8601_duration('PT1H2M30S')
        self.assertEqual(fmt, '1:02:30')
        self.assertEqual(sec, 3750)

        # PT45S -> 0:45, 45s
        fmt, sec = vservice.parse_iso8601_duration('PT45S')
        self.assertEqual(fmt, '0:45')
        self.assertEqual(sec, 45)
