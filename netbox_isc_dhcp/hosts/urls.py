from django.urls import path

from . import views

urlpatterns = [
    path("", views.HostsView.as_view(), name="hosts"),
    path("inline/", views.HostsInlineView.as_view(), name="hosts_inline"),
]
