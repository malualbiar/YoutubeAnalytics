# YT Quid - YouTube Artist Analytics & Monitoring Platform

A full-featured music analytics, channel monitoring, and historical growth intelligence platform built with **Django**, **Django HTML Templates**, **Tailwind CSS**, **Chart.js**, and **SQLite**.

Designed specifically for music managers, record labels, and artists to track YouTube channel growth, video performance, historical view snapshots, milestone unlocks, and comparative analytics directly via the official **YouTube Data API v3**—with zero dependency on DistroKid.

---

## 🌟 Key Features

1. **Artist & Channel Management**:
   - Add/edit artists and connect official YouTube channels via channel URL, `@handle`, or raw Channel ID (`UC...`).
   - Automated channel validation and preview before connection.
2. **Automated Video Discovery & Statistics**:
   - Discovers new uploads from channel playlists.
   - Batch fetches statistics (up to 50 videos per API call) to preserve daily API quotas.
3. **Historical Snapshots & Growth Calculations**:
   - Records periodic snapshots (`VideoStatisticSnapshot` and `ChannelStatisticSnapshot`).
   - Accurately distinguishes **Total Cumulative Views** (YouTube reported) from **Views Gained** (Platform calculated).
   - Computes views gained today, this week, this month, and lifetime growth curves.
4. **Interactive Analytics Dashboard**:
   - Day-by-day views growth trajectory (7D, 30D, 90D, 1Y filters) powered by Chart.js.
   - Top performing tracks ranked by total views, daily gains, weekly gains, or likes.
   - Fastest growing songs (velocity indicators).
   - Milestones feed (celebrates crossing 10K, 50K, 100K, 1M, 5M, 10M views).
5. **Artist & Video Comparisons**:
   - Side-by-side benchmarking matrix for multiple artists or tracks.
   - Comparative multi-line performance charts.
6. **Executive Reports & Data Export**:
   - Custom date-range reports for artists and video catalogs.
   - One-click **CSV download** and **Executive Printable PDF** layouts.
7. **System Health & API Quota Tracking**:
   - Quota usage meter (tracks units consumed against Google's standard 10,000 daily limit).
   - Real-time audit logs of all synchronization runs with execution times and error messages.
8. **Role-Based Access Control (RBAC)**:
   - **Super Admin**: Full platform control, channel connections, user management, and system settings.
   - **Manager**: Artist creation and catalog management.
   - **Viewer**: Read-only access to dashboards, comparisons, and reports.
9. **Global Search (Ctrl + K)**:
   - Instant live search modal indexing artists, tracks, and channels.

---

## 🚀 Quick Start (Local Setup)

### 1. Prerequisites
- Python 3.10+ installed

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optional: Add your Google Cloud `YOUTUBE_API_KEY` in `.env` to enable live syncing with YouTube).*

### 4. Run Migrations & Seed Demo Data
```bash
python manage.py migrate
python manage.py seed_demo_data
```

### 5. Start the Development Server
```bash
python manage.py runserver
```
Open **`http://127.0.0.1:8000/`** in your browser.

---

## 🔑 Demo Accounts

The database comes pre-seeded with realistic artists (*Luna Vance*, *Kairo Beats*, *Nova Sound*, *Aria Vega*), 22+ songs, 30 days of historical snapshots, and 3 demo user roles:

| Role | Email | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin@analytics.com` | `admin123` | Full Control, Channel Sync, User Management |
| **Manager** | `manager@analytics.com` | `manager123` | Artist Management, Reports, Dashboard |
| **Viewer** | `viewer@analytics.com` | `viewer123` | Read-only access to Analytics & Charts |

*(The login page also includes 1-Click Quick Demo Login buttons for immediate testing).*

---

## 📡 YouTube Data API v3 Configuration

1. Visit [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Enable the **YouTube Data API v3** under **APIs & Services > Library**.
4. Create an **API Key** under **APIs & Services > Credentials**.
5. Paste the key in your `.env` file:
   ```env
   YOUTUBE_API_KEY=AIzaSy...
   ```

### Running Live Sync
- **Via Web UI**: Click the **"Sync All Channels"** button in the top navigation bar or **"Sync Now"** in Channels list.
- **Via Command Line**:
  ```bash
  # Sync all monitored channels
  python manage.py sync_youtube_channels

  # Sync a specific channel
  python manage.py sync_youtube_channels --channel-id UCLunaVanceOfficial01
  ```

---

## 🧪 Running Automated Tests

Run the complete test suite (18 unit & view integration tests):
```bash
python manage.py test apps.authentication.test_auth apps.artists.test_artists apps.videos.test_videos apps.youtube.test_youtube apps.analytics.test_analytics apps.analytics.test_views
```

---

## 📁 Project Structure

```
YoutubeAnalytics/
├── manage.py
├── requirements.txt
├── .env.example
├── .env
├── db.sqlite3
├── core/                           # Django project settings & URLs
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── authentication/             # Custom User, JWT/Session auth & RBAC
│   ├── artists/                    # Artist & YouTubeChannel models & views
│   ├── videos/                     # Video & Snapshot models, video library & detail
│   ├── analytics/                  # Core metrics engine, comparisons & global search
│   ├── milestones/                 # Milestones (10K..10M views) & spike alerts
│   ├── reports/                    # CSV & printable report generator
│   └── youtube/                    # YouTube Data API v3 services & quota tracker
├── templates/                      # Tailwind CSS + Chart.js Django templates
│   ├── base.html                   # Sidebar, TopBar, global search modal (Ctrl+K)
│   ├── auth/                       # Login & user management
│   ├── dashboard/                  # Main analytics dashboard
│   ├── artists/                    # Artist profiles & channel connect
│   ├── videos/                     # Video library & track deep-dive
│   ├── comparisons/                # Artist & Video comparisons
│   ├── reports/                    # Custom date-range reports & export
│   ├── milestones/                 # Milestones timeline & notifications
│   └── system/                     # API quota tracker, sync logs & settings
└── static/
    └── css/styles.css
```