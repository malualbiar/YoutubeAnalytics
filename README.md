# YT Quid - YouTube Artist Analytics, AI Music Radar & Video Studio Platform

A full-featured music analytics, channel monitoring, historical growth intelligence, AI discovery radar, and automated video rendering platform built with **Django**, **Tailwind CSS**, **Chart.js**, **Waitress**, and **Electron**.

Available as both a **Web Server** and a **Standalone Native Windows Desktop Application** (`.exe` Installer & Portable).

---

## 📥 Download Desktop Application (Windows)

Get the latest version of YT Quid for Windows directly from the GitHub releases:

| Package | Download Link | Description |
| :--- | :--- | :--- |
| **Windows Installer** | 📦 [**Download `YT Quid Setup.exe`**](https://github.com/malualbiar/YoutubeAnalytics/releases/latest) | Recommended. Full installer with Desktop & Start Menu shortcuts, auto-updater, and uninstaller. |
| **Portable Version** | ⚡ [**Download `YT Quid Portable.exe`**](https://github.com/malualbiar/YoutubeAnalytics/releases/latest) | Zero-installation standalone executable. Run directly from any folder or USB drive. |
| **All Releases & Notes** | 📋 [**View GitHub Releases**](https://github.com/malualbiar/YoutubeAnalytics/releases) | Release notes, changelog history, and SHA-256 checksums. |

---

## Key Features

### 1. 📊 Interactive Analytics & Catalog Monitoring
- **Real-Time Channel & Video Tracking**: Connect official YouTube channels via channel URL, `@handle`, or raw Channel ID (`UC...`).
- **Growth Calculations & Snapshots**: Accurately tracks **Total Cumulative Views** vs. **Views Gained** (today, this week, this month, 90D, 1Y, all-time).
- **Side-by-Side Comparisons**: Multi-artist and multi-video benchmarking matrices with multi-line growth charts.
- **Milestones & Velocity**: Milestone unlock notifications (10K, 50K, 100K, 1M, 5M, 10M views) with daily velocity indicators.
- **Daily Upload Tracker**: 30-day activity heatmap, streak counter, and customizable posting goals.
- **Executive Reports**: One-click CSV and printable PDF export.

### 2. 📡 AI Music Discovery Radar (`/radar/`)
- **Granular Time Filtering**: Real-time discovery of breakout AI music (Suno, Udio, Lofi, Synthwave, Hip-Hop, Pop, Rock) published in the past 30m, 1h, 6h, 12h, 24h, 48h, 7d, or 30d.
- **Velocity Arbitrage**: Sort by views/hour or filter by underdogs (<10K views) to catch rising trends before they saturate.
- **Lossless Extraction**: 1-click lossless WAV / MP3 audio downloader powered by `yt-dlp`.
- **Direct Studio Bridge**: 1-click export from Radar into the Video Studio.

### 3. 🎬 Creator Studio & Viral Shorts Factory (`/studio/`)
- **Short Video Generator & Multi-Clip Chopper (`/studio/shorts/`)**:
  - **1 Long Video → Multiple Shorts**: Upload any long video (.mp4, .mov, .mkv) or track and chop it into multiple vertical 9:16 clips (15s, 30s, 60s, or custom intervals).
  - **Move & Preview Chops**: Interactive visual timeline to adjust boundaries, reorder chops, and preview segments in the player before rendering.
  - **9:16 Vertical Re-Framing**: Blurred ambient backdrop, center crop, or letterbox modes.
  - **Viral Hook Badges & Typography**: Custom banner pills (`"Wait for the beat drop! 🎧"`), top part badges, and channel watermark CTA.
  - **Batch & ZIP Export**: Download individual vertical shorts or all chops in a single ZIP package.
- **Non-Stop Continuous Mix Maker (`/studio/mix/`)**:
  - DJ-style seamless multi-track blending with 5 crossfade curves (Equal-Power Quarter-Sine, Linear, Triangular, Exponential, Quick Club Cut).
  - Automatic YouTube chapters and descriptions generator.
- **1-Hour Extended Study Loops & Visualizers**:
  - 60-minute seamless watch-time loops and 1080p official visualizers.

---

## 💻 Standalone Desktop Application

YT Quid runs as a native desktop application with an embedded Python/Django WSGI server powered by **Waitress** and an **Electron** frontend.

👉 **[Download the Latest Windows Release (v1.0.0)](https://github.com/malualbiar/YoutubeAnalytics/releases/latest)**

### Desktop Architecture
- **Zero Configuration**: Automatically applies database migrations and seeds initial demo data on first launch.
- **Data Persistence**: Stores the SQLite database (`db.sqlite3`), `.env` overrides, and generated media/video outputs in `%APPDATA%\YTQuid\` (or `~/.config/ytquid/` on Linux/macOS).
- **Bundled Binaries**: Ships with embedded Python runtime dependencies and bundled FFmpeg.

---

## 🛠️ Building the Desktop App Locally

### 1. Prerequisites
- Python 3.10+ installed
- Node.js 18+ and npm installed

### 2. One-Click Build (Windows)
Run the automated build batch script from the project root:
```cmd
build_desktop.bat
```

### 3. Manual Step-by-Step Build
```bash
# 1. Install dependencies
pip install -r requirements.txt
npm install

# 2. Package the backend into dist-backend/server/
npm run build:backend

# 3. Test the packaged backend executable
dist-backend\server\server.exe --test

# 4. Build the Electron Desktop Installer and Portable App
npm run dist
```

### Build Artifacts
Outputs are generated in `dist-electron/`:
- **`YT Quid Setup 1.0.0.exe`**: Full NSIS Windows installer (desktop shortcut, start menu shortcut, uninstaller).
- **`YT Quid 1.0.0.exe`**: Standalone zero-install portable executable.

---

## 🚀 CI/CD Automated Release Workflows

The repository includes a GitHub Actions workflow located at [`.github/workflows/release-desktop.yml`](.github/workflows/release-desktop.yml) for building and publishing desktop releases.

### How to Trigger a Release
1. **Via Git Tag**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
2. **Via GitHub Actions Web UI**:
   - Go to the **Actions** tab on GitHub.
   - Select **Release Desktop App**.
   - Click **Run workflow** and specify the version tag (e.g. `v1.0.0`).

### Automated Workflow Pipeline
1. Sets up clean Windows runners with Python 3.11 and Node.js 20.
2. Compiles the embedded Django backend via PyInstaller.
3. Builds the NSIS Installer and Portable Executables via `electron-builder`.
4. Calculates SHA-256 checksums (`checksums-sha256.txt`).
5. Publishes a new **GitHub Release** with all executable assets attached.

---

## 🌐 Running in Web Server Mode

You can also run YT Quid as a standard web application:

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure .env
cp .env.example .env

# 3. Migrate and seed demo data
python manage.py migrate
python manage.py seed_demo_data

# 4. Start local server
python manage.py runserver
```
Visit **`http://127.0.0.1:8000/`** in your browser.

---

## Demo Accounts

The database comes pre-seeded with 4 active artists (*Luna Vance*, *Kairo Beats*, *Nova Sound*, *Aria Vega*), 22+ songs, 30 days of historical snapshots, and 3 demo user roles:

| Role | Email | Password | Permissions |
| :--- | :--- | :--- | :--- |
| **Super Admin** | `admin@analytics.com` | `admin123` | Full Control, Channel Sync, User Management |
| **Manager** | `manager@analytics.com` | `manager123` | Artist Management, Reports, Dashboard |
| **Viewer** | `viewer@analytics.com` | `viewer123` | Read-only access to Analytics & Charts |

---

## Running Automated Tests

Run the test suite:
```bash
python manage.py test apps.authentication.test_auth apps.artists.test_artists apps.videos.test_videos apps.youtube.test_youtube apps.analytics.test_analytics apps.analytics.test_views apps.studio.test_mix_engine apps.radar.tests
```

---

## Project Structure

```
YoutubeAnalytics/
├── .github/workflows/
│   └── release-desktop.yml         # CI/CD automated desktop release workflow
├── build_desktop.bat               # 1-click Windows desktop compilation script
├── main.js                         # Electron main process & server launcher
├── preload.js                      # Electron secure context bridge
├── server.py                       # Embedded Waitress WSGI server launcher
├── server.spec                     # PyInstaller configuration & asset bundler
├── package.json                    # Electron build configuration & scripts
├── requirements.txt                # Python backend dependencies
├── bin/
│   └── ffmpeg.exe                  # Bundled FFmpeg multimedia engine
├── core/                           # Django project settings & URLs
├── apps/
│   ├── authentication/             # Custom User, Auth & RBAC
│   ├── artists/                    # Artist & YouTubeChannel models & views
│   ├── videos/                     # Video & Snapshot models, catalog & detail
│   ├── analytics/                  # Core metrics engine & comparisons
│   ├── milestones/                 # Milestones & velocity alerts
│   ├── reports/                    # CSV & printable report generator
<<<<<<< HEAD
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
=======
│   ├── youtube/                    # YouTube Data API v3 services & quota tracker
│   ├── studio/                     # Video Studio & Non-Stop Mix Engine
│   └── radar/                      # AI Music Discovery Radar
├── templates/                      # Tailwind CSS Django templates
└── dist-electron/                  # Compiled desktop installer & portable .exe
```
>>>>>>> e0da034 (Release: Compile desktop app, add GitHub Actions release workflow, update README with download links)
