"""
Django settings for YoutubeAnalytics project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = Path(getattr(sys, '_MEIPASS', os.path.dirname(sys.executable)))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'django-insecure-youtube-artist-analytics-secret-key-change-in-production'
)

DEBUG = os.getenv('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = list(set([h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',') if h.strip()] + ['testserver', '127.0.0.1', 'localhost']))

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # Local Apps
    'apps.authentication.apps.AuthenticationConfig',
    'apps.artists.apps.ArtistsConfig',
    'apps.videos.apps.VideosConfig',
    'apps.analytics.apps.AnalyticsConfig',
    'apps.milestones.apps.MilestonesConfig',
    'apps.reports.apps.ReportsConfig',
    'apps.youtube.apps.YoutubeConfig',
    'apps.studio.apps.StudioConfig',
    'apps.radar.apps.RadarConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.analytics.context_processors.global_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database: SQLite for simple, lightweight local setup
import sys
import shutil

if getattr(sys, 'frozen', False) or os.getenv('YT_QUID_DESKTOP') == '1':
    DATA_DIR = Path(os.getenv('APPDATA', os.path.expanduser('~'))) / 'YTQuid' if os.name == 'nt' else Path.home() / '.config' / 'ytquid'
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH = DATA_DIR / 'db.sqlite3'
    # Seed from local db if first run
    if not DB_PATH.exists() and (BASE_DIR / 'db.sqlite3').exists():
        try:
            shutil.copy2(BASE_DIR / 'db.sqlite3', DB_PATH)
        except Exception:
            pass
    if (DATA_DIR / '.env').exists():
        load_dotenv(DATA_DIR / '.env')
else:
    DB_PATH = BASE_DIR / 'db.sqlite3'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': DB_PATH,
    }
}

# Custom User Model
AUTH_USER_MODEL = 'authentication.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = os.getenv('TIME_ZONE', 'UTC')
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Authentication URLs
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

# YouTube API Settings
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', '')
YOUTUBE_API_SERVICE_NAME = 'youtube'
YOUTUBE_API_VERSION = 'v3'
SYNC_INTERVAL_HOURS = int(os.getenv('SYNC_INTERVAL_HOURS', '6'))
