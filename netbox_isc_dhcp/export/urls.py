from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExportPageView.as_view(), name="export"),
    path("regenerate/", views.ExportRegenView.as_view(), name="export_regen"),
    path("manifest.json", views.ManifestView.as_view(), name="export_manifest"),
    path("file/<path:path>", views.FileView.as_view(), name="export_file"),
]
