from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard_view, name='dashboard'),
    path('comparisons/artists/', views.artist_comparison_view, name='artist_comparison'),
    path('comparisons/videos/', views.video_comparison_view, name='video_comparison'),
    path('api/search/', views.global_search_view, name='global_search_api'),
]
