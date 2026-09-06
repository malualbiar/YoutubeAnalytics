from django.urls import path
from . import views

urlpatterns = [
    # Single 1-Hour Loop / Visualizer routes
    path('studio/', views.studio_home_view, name='studio_home'),
    path('studio/render/', views.studio_render_view, name='studio_render'),
    path('studio/<int:pk>/delete/', views.studio_delete_view, name='studio_delete'),

    # Non-Stop Continuous Long Mix Maker routes
    path('studio/mix/', views.mix_maker_view, name='mix_maker'),
    path('studio/mix/render/', views.mix_render_view, name='mix_render'),
    path('studio/mix/<int:pk>/', views.mix_detail_view, name='mix_detail'),
    path('studio/mix/<int:pk>/delete/', views.mix_delete_view, name='mix_delete'),
    path('studio/mix/api/search/', views.mix_import_api, name='mix_import_api'),
]
