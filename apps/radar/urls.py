from django.urls import path
from . import views

urlpatterns = [
    path('radar/', views.radar_feed_view, name='radar_feed'),
    path('radar/download/', views.download_audio_view, name='radar_download_audio'),
    path('radar/import-studio/', views.import_to_studio_view, name='radar_import_studio'),
]
