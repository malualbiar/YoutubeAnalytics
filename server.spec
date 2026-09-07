# -*- mode: python ; coding: utf-8 -*-

import os

datas = [
    ('apps', 'apps'),
    ('core', 'core'),
    ('templates', 'templates'),
    ('static', 'static'),
    ('bin', 'bin'),
]

if os.path.exists('.env'):
    datas.append(('.env', '.'))
elif os.path.exists('.env.example'):
    datas.append(('.env.example', '.'))

if os.path.exists('db.sqlite3'):
    datas.append(('db.sqlite3', '.'))

hiddenimports = [
    'django',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.staticfiles.handlers',
    'django.contrib.humanize',
    'django.db.models',
    'waitress',
    'googleapiclient',
    'googleapiclient.discovery',
    'google_auth_httplib2',
    'dotenv',
    'PIL',
    'PIL.Image',
    'PIL.ImageFilter',
    'PIL.ImageEnhance',
    'yt_dlp',
    'imageio_ffmpeg',
    'apps.authentication',
    'apps.authentication.apps',
    'apps.artists',
    'apps.artists.apps',
    'apps.videos',
    'apps.videos.apps',
    'apps.analytics',
    'apps.analytics.apps',
    'apps.analytics.context_processors',
    'apps.milestones',
    'apps.milestones.apps',
    'apps.reports',
    'apps.reports.apps',
    'apps.youtube',
    'apps.youtube.apps',
    'apps.studio',
    'apps.studio.apps',
    'apps.radar',
    'apps.radar.apps',
]

a = Analysis(
    ['server.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchvision', 'torchaudio', 'matplotlib',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'pandas', 'scipy', 'sklearn', 'tkinter',
        'IPython', 'jupyter', 'pytest'
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='server',
)
