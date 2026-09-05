from django.urls import path
from . import views

urlpatterns = [
    path('milestones/', views.milestones_list_view, name='milestones_list'),
    path('notifications/', views.notifications_list_view, name='notifications_list'),
]
