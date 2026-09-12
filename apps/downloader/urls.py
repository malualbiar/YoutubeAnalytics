from django.urls import path
from . import views

urlpatterns = [
    path('downloader/', views.downloader_home_view, name='downloader_home'),
    path('downloader/fetch-info/', views.downloader_fetch_info_api, name='downloader_fetch_info'),
    path('downloader/start/', views.downloader_start_view, name='downloader_start'),
    path('downloader/<int:pk>/progress/', views.downloader_progress_api, name='downloader_progress'),
    path('downloader/<int:pk>/delete/', views.downloader_delete_view, name='downloader_delete'),
    path('downloader/<int:pk>/download/', views.downloader_file_view, name='downloader_file'),
    path('downloader/<int:pk>/prepare-lyrics/', views.prepare_lyrics_api, name='downloader_prepare_lyrics'),
]
