from django.urls import path
from . import views

urlpatterns = [
    path('channels/', views.channels_list_view, name='channels_list'),
    path('channels/<int:pk>/sync/', views.trigger_sync_channel_view, name='sync_channel'),
    path('channels/sync-all/', views.trigger_sync_all_view, name='sync_all_channels'),
    path('system/logs/', views.sync_logs_view, name='sync_logs'),
    path('system/api-usage/', views.api_usage_view, name='api_usage'),
    path('system/settings/', views.system_settings_view, name='system_settings'),
]
