from django.urls import path
from . import views

urlpatterns = [
    path('reports/', views.reports_view, name='reports'),
    path('reports/export/csv/', views.export_report_csv, name='export_report_csv'),
    path('reports/printable/', views.printable_report_view, name='printable_report'),
]
