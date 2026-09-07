from django.urls import path
from . import views

urlpatterns = [
    path('publishing/', views.publisher_dashboard_view, name='publishing_dashboard'),
    path('publishing/queue/', views.queue_list_view, name='publishing_queue'),
    path('publishing/oauth/connect/', views.oauth_connect_view, name='publishing_oauth_connect'),
    path('publishing/oauth/callback/', views.oauth_callback_view, name='publishing_oauth_callback'),
    path('publishing/oauth/disconnect/<int:account_id>/', views.oauth_disconnect_view, name='publishing_oauth_disconnect'),
    path('publishing/oauth/default/<int:account_id>/', views.oauth_set_default_view, name='publishing_oauth_default'),
    path('publishing/jobs/create/', views.create_job_view, name='publishing_create_job'),
    path('publishing/jobs/batch-shorts/<int:project_id>/', views.batch_queue_shorts_view, name='publishing_batch_shorts'),
    path('publishing/jobs/status-api/', views.job_status_api, name='publishing_job_status_api'),
    path('publishing/jobs/<int:job_id>/cancel/', views.cancel_job_view, name='publishing_cancel_job'),
    path('publishing/jobs/<int:job_id>/retry/', views.retry_job_view, name='publishing_retry_job'),
    path('publishing/jobs/<int:job_id>/delete/', views.delete_job_view, name='publishing_delete_job'),
]
