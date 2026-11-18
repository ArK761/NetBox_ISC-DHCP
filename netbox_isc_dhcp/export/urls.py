from django.urls import path

from . import views

urlpatterns = [
    path("", views.ExportPageView.as_view(), name="export"),
    path("regenerate/", views.ExportRegenView.as_view(), name="export_regen"),
    path("manifest.json", views.ManifestView.as_view(), name="export_manifest"),
    path("agent/", views.PlanView.as_view(), name="export_plan"),
    path("plan/", views.PlanView.as_view()),  # old address (v0.26)
    path("report/", views.ReportView.as_view(), name="export_report"),
    path("agent-self/", views.AgentSelfView.as_view(), name="export_agent_self"),
    path("bundle/", views.BundleView.as_view(), name="export_bundle"),
    path("file/<path:path>", views.FileView.as_view(), name="export_file"),
]
