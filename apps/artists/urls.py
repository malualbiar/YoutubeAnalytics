from django.urls import path
from . import views

urlpatterns = [
    path('artists/', views.artist_list_view, name='artist_list'),
    path('artists/create/', views.artist_create_view, name='artist_create'),
    path('artists/<int:pk>/', views.artist_detail_view, name='artist_detail'),
    path('artists/<int:pk>/edit/', views.artist_edit_view, name='artist_edit'),
    path('artists/<int:pk>/delete/', views.artist_delete_view, name='artist_delete'),
    path('artists/<int:pk>/connect-channel/', views.connect_channel_view, name='connect_channel'),
    path('artists/<int:pk>/disconnect-channel/', views.disconnect_channel_view, name='disconnect_channel'),
]
