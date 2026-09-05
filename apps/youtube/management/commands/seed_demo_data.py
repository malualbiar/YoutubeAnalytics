import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from apps.authentication.models import User
from apps.artists.models import Artist, YouTubeChannel
from apps.videos.models import Video, VideoStatisticSnapshot, ChannelStatisticSnapshot
from apps.milestones.models import VideoMilestone, NotificationLog
from apps.youtube.models import YouTubeApiUsage, SyncLog, SystemSettings

class Command(BaseCommand):
    help = 'Seed the database with realistic demo music artists, YouTube channels, videos, 30-day snapshot history, and milestones'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Seeding YouTube Artist Analytics with realistic demo data...'))

        with transaction.atomic():
            # 1. Users
            admin_user, _ = User.objects.get_or_create(
                email='admin@analytics.com',
                defaults={
                    'username': 'admin',
                    'role': User.Role.SUPER_ADMIN,
                    'first_name': 'Super',
                    'last_name': 'Admin',
                    'is_staff': True,
                    'is_superuser': True,
                    'organization': 'Apex Music Group'
                }
            )
            admin_user.set_password('admin123')
            admin_user.save()

            manager_user, _ = User.objects.get_or_create(
                email='manager@analytics.com',
                defaults={
                    'username': 'manager',
                    'role': User.Role.MANAGER,
                    'first_name': 'Sarah',
                    'last_name': 'Connor',
                    'is_staff': False,
                    'organization': 'Apex Music Group'
                }
            )
            manager_user.set_password('manager123')
            manager_user.save()

            viewer_user, _ = User.objects.get_or_create(
                email='viewer@analytics.com',
                defaults={
                    'username': 'viewer',
                    'role': User.Role.VIEWER,
                    'first_name': 'John',
                    'last_name': 'Doe',
                    'is_staff': False,
                    'organization': 'Indie Label'
                }
            )
            viewer_user.set_password('viewer123')
            viewer_user.save()

            self.stdout.write(self.style.SUCCESS('  [OK] Created demo user accounts (admin@analytics.com, manager@analytics.com, viewer@analytics.com)'))

            # System Settings
            SystemSettings.get_settings()

            # 2. Artists & Channels data definition
            artists_data = [
                {
                    'name': 'Luna Vance',
                    'stage_name': 'Luna Vance',
                    'genre': 'Pop / R&B',
                    'description': 'Global pop sensation known for ethereal vocals and chart-topping synth-pop anthems.',
                    'profile_image': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=600&q=80',
                    'channel_id': 'UCLunaVanceOfficial01',
                    'channel_name': 'Luna Vance Official',
                    'channel_url': 'https://www.youtube.com/@LunaVance',
                    'thumbnail_url': 'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=400&q=80',
                    'subscriber_count': 1_450_000,
                    'total_views': 48_250_000,
                    'video_count': 8,
                    'videos': [
                        ('Midnight Mirage (Official Music Video)', 'd1A8j9K3L4M', 12_450_000, 485_000, 14_200, '3:42', 222, 120, 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=600&q=80'),
                        ('Echoes in the Rain (Lyric Video)', 'e2B7k8L9M0N', 6_820_000, 240_000, 8_900, '4:05', 245, 90, 'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?auto=format&fit=crop&w=600&q=80'),
                        ('Velvet Sky (Live Acoustic Session)', 'f3C6j7K8L9O', 4_150_000, 185_000, 6_400, '3:18', 198, 60, 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=600&q=80'),
                        ('Dancing with Shadows', 'g4D5i6J7K8P', 8_900_000, 390_000, 11_300, '3:55', 235, 45, 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=600&q=80'),
                        ('Golden Hour Fantasy (Visualizer)', 'h5E4h5I6J7Q', 3_200_000, 142_000, 4_100, '2:50', 170, 25, 'https://images.unsplash.com/photo-1465847899084-d164df4dedc6?auto=format&fit=crop&w=600&q=80'),
                        ('Neon Heartbeat (Remix)', 'i6F3g4H5I6R', 1_850_000, 95_000, 2_800, '3:30', 210, 12, 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=600&q=80'),
                        ('Sweet Illusion (Official Audio)', 'j7G2f3G4H5S', 980_000, 52_000, 1_450, '3:10', 190, 5, 'https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?auto=format&fit=crop&w=600&q=80'),
                    ]
                },
                {
                    'name': 'Kairo Mensah',
                    'stage_name': 'Kairo Beats',
                    'genre': 'Afrobeats / Amapiano',
                    'description': 'Lagos-born international producer and recording artist blending energetic log drums with smooth afro-fusion melodies.',
                    'profile_image': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=600&q=80',
                    'channel_id': 'UCKairoBeatsMusic02',
                    'channel_name': 'Kairo Beats Official',
                    'channel_url': 'https://www.youtube.com/@KairoBeats',
                    'thumbnail_url': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=400&q=80',
                    'subscriber_count': 890_000,
                    'total_views': 32_100_000,
                    'video_count': 6,
                    'videos': [
                        ('Lagos Sunset (ft. Starboy)', 'k8H1e2F3G4T', 9_850_000, 420_000, 12_800, '3:15', 195, 140, 'https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?auto=format&fit=crop&w=600&q=80'),
                        ('Fever Pitch (Official Video)', 'l9I0d1E2F3U', 7_400_000, 310_000, 9_200, '3:35', 215, 80, 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=600&q=80'),
                        ('Amapiano Waves Pt. 2', 'm0J9c0D1E2V', 5_600_000, 245_000, 7_600, '4:20', 260, 50, 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=600&q=80'),
                        ('Shine Forever (Dance Video)', 'n1K8b9C0D1W', 3_900_000, 168_000, 5_100, '3:05', 185, 30, 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=600&q=80'),
                        ('Vibration State of Mind', 'o2L7a8B9C0X', 2_450_000, 115_000, 3_400, '3:40', 220, 15, 'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?auto=format&fit=crop&w=600&q=80'),
                        ('Summer Groove 2026', 'p3M6z7A8B9Y', 1_200_000, 68_000, 2_100, '2:55', 175, 4, 'https://images.unsplash.com/photo-1465847899084-d164df4dedc6?auto=format&fit=crop&w=600&q=80'),
                    ]
                },
                {
                    'name': 'Nova Sound Syndicate',
                    'stage_name': 'Nova Sound',
                    'genre': 'Electronic / Synthwave',
                    'description': 'Electronic music collective producing retro-futuristic soundscapes and energetic festival anthems.',
                    'profile_image': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=600&q=80',
                    'channel_id': 'UCNovaSoundOfficial03',
                    'channel_name': 'Nova Sound Syndicate',
                    'channel_url': 'https://www.youtube.com/@NovaSound',
                    'thumbnail_url': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=400&q=80',
                    'subscriber_count': 420_000,
                    'total_views': 18_700_000,
                    'video_count': 5,
                    'videos': [
                        ('Cyber City Horizons', 'q4N5y6Z7A8Z', 6_450_000, 290_000, 7_800, '4:12', 252, 100, 'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?auto=format&fit=crop&w=600&q=80'),
                        ('Overdrive Protocol', 'r5O4x5Y6Z7A', 4_200_000, 185_000, 4_900, '3:50', 230, 65, 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=600&q=80'),
                        ('Starlight Velocity', 's6P3w4X5Y6B', 3_100_000, 134_000, 3_500, '3:25', 205, 40, 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=600&q=80'),
                        ('Quantum Dreams (Live Mix)', 't7Q2v3W4X5C', 2_150_000, 92_000, 2_400, '5:10', 310, 20, 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=600&q=80'),
                        ('Neon Velocity Reloaded', 'u8R1u2V3W4D', 850_000, 41_000, 1_100, '3:45', 225, 7, 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?auto=format&fit=crop&w=600&q=80'),
                    ]
                },
                {
                    'name': 'Aria Vega',
                    'stage_name': 'Aria Vega',
                    'genre': 'Indie / Alternative',
                    'description': 'Singer-songwriter crafting intimate indie-folk stories with soulful acoustic arrangements.',
                    'profile_image': 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=600&q=80',
                    'channel_id': 'UCAriaVegaOfficial04',
                    'channel_name': 'Aria Vega Music',
                    'channel_url': 'https://www.youtube.com/@AriaVega',
                    'thumbnail_url': 'https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=400&q=80',
                    'subscriber_count': 215_000,
                    'total_views': 8_450_000,
                    'video_count': 4,
                    'videos': [
                        ('Wildflower Meadow', 'v9S0t1U2V3E', 3_600_000, 165_000, 4_700, '3:30', 210, 110, 'https://images.unsplash.com/photo-1465847899084-d164df4dedc6?auto=format&fit=crop&w=600&q=80'),
                        ('Paper Boats on the River', 'w0T9s0T1U2F', 2_450_000, 112_000, 3_100, '3:45', 225, 70, 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?auto=format&fit=crop&w=600&q=80'),
                        ('Winter Whispers (Acoustic)', 'x1U8r9S0T1G', 1_450_000, 68_000, 1_900, '4:00', 240, 35, 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=600&q=80'),
                        ('Autumn Leaves & Coffee', 'y2V7q8R9S0H', 720_000, 38_000, 950, '3:10', 190, 8, 'https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?auto=format&fit=crop&w=600&q=80'),
                    ]
                }
            ]

            now = timezone.now()
            created_videos = []

            for a_info in artists_data:
                artist, _ = Artist.objects.update_or_create(
                    stage_name=a_info['stage_name'],
                    defaults={
                        'name': a_info['name'],
                        'genre': a_info['genre'],
                        'description': a_info['description'],
                        'profile_image': a_info['profile_image'],
                        'youtube_channel_id': a_info['channel_id'],
                        'youtube_channel_url': a_info['channel_url'],
                        'status': Artist.Status.ACTIVE
                    }
                )

                channel, _ = YouTubeChannel.objects.update_or_create(
                    channel_id=a_info['channel_id'],
                    defaults={
                        'artist': artist,
                        'channel_name': a_info['channel_name'],
                        'channel_url': a_info['channel_url'],
                        'thumbnail_url': a_info['thumbnail_url'],
                        'description': a_info['description'],
                        'subscriber_count': a_info['subscriber_count'],
                        'total_views': a_info['total_views'],
                        'video_count': a_info['video_count'],
                        'uploads_playlist_id': f"UU{a_info['channel_id'][2:]}",
                        'sync_status': YouTubeChannel.SyncStatus.SUCCESS,
                        'last_synced_at': now,
                    }
                )

                for v_title, v_id, v_views, v_likes, v_comments, v_dur, v_dur_sec, days_old, v_thumb in a_info['videos']:
                    published_date = now - timedelta(days=days_old)
                    video, _ = Video.objects.update_or_create(
                        youtube_video_id=v_id,
                        defaults={
                            'channel': channel,
                            'artist': artist,
                            'title': v_title,
                            'thumbnail_url': v_thumb,
                            'published_at': published_date,
                            'duration': v_dur,
                            'duration_seconds': v_dur_sec,
                            'video_url': f"https://www.youtube.com/watch?v={v_id}",
                            'current_views': v_views,
                            'current_likes': v_likes,
                            'current_comments': v_comments,
                            'last_synced_at': now,
                            'is_active': True,
                        }
                    )
                    created_videos.append(video)

            self.stdout.write(self.style.SUCCESS(f'  [OK] Created {len(artists_data)} artists and {len(created_videos)} videos'))

            # 3. Generate 30 days of historical snapshots with realistic growth curves
            self.stdout.write('  Generating 30 days of historical time series snapshots...')
            
            # Clear old snapshots for a clean seed
            VideoStatisticSnapshot.objects.all().delete()
            ChannelStatisticSnapshot.objects.all().delete()
            VideoMilestone.objects.all().delete()
            NotificationLog.objects.all().delete()

            for video in created_videos:
                # Base views 30 days ago = roughly 60-80% of current views
                growth_rate = random.uniform(0.65, 0.85)
                start_views = int(video.current_views * growth_rate)
                views_to_gain = video.current_views - start_views
                
                # Distribute views across 30 days with daily noise and weekend boosts
                daily_weights = []
                for day_idx in range(30):
                    day_date = now - timedelta(days=(29 - day_idx))
                    weekday = day_date.weekday()
                    weight = 1.0
                    if weekday in [4, 5, 6]:  # Fri, Sat, Sun boost
                        weight += random.uniform(0.3, 0.6)
                    weight += random.uniform(-0.2, 0.3)
                    daily_weights.append(max(0.2, weight))

                total_weight = sum(daily_weights)
                running_views = start_views

                for day_idx in range(30):
                    day_date = now - timedelta(days=(29 - day_idx))
                    day_gain = int((daily_weights[day_idx] / total_weight) * views_to_gain)
                    # Last day ensure it matches exactly current_views
                    if day_idx == 29:
                        day_gain = max(0, video.current_views - running_views)
                        running_views = video.current_views
                    else:
                        running_views += day_gain

                    likes_gain = int(day_gain * random.uniform(0.03, 0.05))
                    comments_gain = int(day_gain * random.uniform(0.001, 0.002))

                    likes_at_day = int((running_views / video.current_views) * video.current_likes)
                    comments_at_day = int((running_views / video.current_views) * video.current_comments)

                    VideoStatisticSnapshot.objects.create(
                        video=video,
                        recorded_at=day_date,
                        views=running_views,
                        likes=likes_at_day,
                        comments=comments_at_day,
                        views_change=day_gain,
                        likes_change=likes_gain,
                        comments_change=comments_gain
                    )

                # Set today's, this week's, this month's cached view gains on video
                v_today_gain = VideoStatisticSnapshot.objects.filter(
                    video=video,
                    recorded_at__gte=now - timedelta(days=1)
                ).first()
                video.views_today = v_today_gain.views_change if v_today_gain else int(video.current_views * 0.01)

                v_week_gain = VideoStatisticSnapshot.objects.filter(
                    video=video,
                    recorded_at__gte=now - timedelta(days=7)
                )
                video.views_this_week = sum(s.views_change for s in v_week_gain)

                video.views_this_month = views_to_gain
                video.save()

                # Milestones for this video
                thresholds = [10_000, 50_000, 100_000, 250_000, 500_000, 1_000_000, 5_000_000, 10_000_000]
                for th in thresholds:
                    if video.current_views >= th:
                        m_type = VideoMilestone.MilestoneType.CUSTOM
                        for choice_val, choice_label in VideoMilestone.MilestoneType.choices:
                            if str(th) in choice_val or (th == 1_000_000 and '1M' in choice_val) or (th == 5_000_000 and '5M' in choice_val) or (th == 10_000_000 and '10M' in choice_val):
                                m_type = choice_val
                                break

                        # Date reached approx
                        days_ago = random.randint(1, 28)
                        VideoMilestone.objects.create(
                            video=video,
                            milestone_type=m_type,
                            threshold=th,
                            views_at_milestone=th + random.randint(100, 2000),
                            reached_at=now - timedelta(days=days_ago),
                            notified=True
                        )

            # Channel Snapshots for 30 days
            for channel in YouTubeChannel.objects.all():
                ch_views = channel.total_views
                for day_idx in range(30):
                    day_date = now - timedelta(days=(29 - day_idx))
                    daily_ch_gain = random.randint(15_000, 85_000)
                    ChannelStatisticSnapshot.objects.create(
                        channel=channel,
                        recorded_at=day_date,
                        subscriber_count=channel.subscriber_count - (30 - day_idx) * random.randint(50, 200),
                        total_views=ch_views - (30 - day_idx) * daily_ch_gain,
                        video_count=channel.video_count,
                        subscriber_change=random.randint(50, 250),
                        view_change=daily_ch_gain,
                        video_change=0
                    )

            self.stdout.write(self.style.SUCCESS('  [OK] Generated 30 days of snapshots and historical data'))

            # 4. Notifications & Alerts
            NotificationLog.objects.create(
                notification_type=NotificationLog.NotificationType.MILESTONE,
                title="Milestone: Midnight Mirage",
                message="Midnight Mirage by Luna Vance just crossed 10,000,000 views!",
                link="/videos/1/",
                created_at=now - timedelta(hours=3),
                is_read=False
            )
            NotificationLog.objects.create(
                notification_type=NotificationLog.NotificationType.SPIKE_ALERT,
                title="Spike Alert: Lagos Sunset",
                message="Lagos Sunset (ft. Starboy) gained +84,200 views in the last 24 hours.",
                link="/videos/8/",
                created_at=now - timedelta(hours=8),
                is_read=False
            )
            NotificationLog.objects.create(
                notification_type=NotificationLog.NotificationType.SYSTEM,
                title="Scheduled Sync Complete",
                message="All 4 monitored channels were successfully synchronized.",
                created_at=now - timedelta(hours=14),
                is_read=True
            )

            # 5. API Usage Logs
            for day_idx in range(14):
                d_date = (now - timedelta(days=day_idx)).date()
                YouTubeApiUsage.objects.create(
                    date=d_date,
                    quota_used=random.randint(24, 150),
                    request_count=random.randint(8, 25),
                )

            # 6. Sync Logs
            for channel in YouTubeChannel.objects.all():
                SyncLog.objects.create(
                    channel=channel,
                    channel_name_cached=channel.channel_name,
                    started_at=now - timedelta(hours=random.randint(1, 12)),
                    completed_at=now - timedelta(hours=random.randint(1, 12)) + timedelta(seconds=random.randint(3, 8)),
                    status=SyncLog.Status.SUCCESS,
                    videos_found=channel.videos.count(),
                    new_videos=0,
                    videos_updated=channel.videos.count(),
                    snapshots_created=channel.videos.count(),
                    duration_seconds=round(random.uniform(2.5, 5.8), 2)
                )

            self.stdout.write(self.style.SUCCESS('\n======================================================='))
            self.stdout.write(self.style.SUCCESS('YOUTUBE ARTIST ANALYTICS DATABASE SEEDED SUCCESSFULLY!'))
            self.stdout.write(self.style.SUCCESS('======================================================='))
            self.stdout.write('Demo Logins:')
            self.stdout.write('  1. Super Admin: admin@analytics.com   / admin123')
            self.stdout.write('  2. Manager:     manager@analytics.com / manager123')
            self.stdout.write('  3. Viewer:      viewer@analytics.com  / viewer123')
            self.stdout.write('=======================================================\n')
