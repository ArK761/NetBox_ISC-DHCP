from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExportPageView.as_view(), name="export"),
    path("regenerate/", views.ExportRegenView.as_view(), name="export_regen"),
    path("manifest.json", views.ManifestView.as_view(), name="export_manifest"),
    path("plan/", views.PlanView.as_view(), name="export_plan"),
    path("report/", views.ReportView.as_view(), name="export_report"),
    path("file/<path:path>", views.FileView.as_view(), name="export_file"),
]
