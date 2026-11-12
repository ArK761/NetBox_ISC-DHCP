from django.urls import path

from . import views

urlpatterns = [
    path("", views.HostsView.as_view(), name="hosts"),
    path("inline/", views.HostsInlineView.as_view(), name="hosts_inline"),
    path("group/<int:pk>/", views.HostGroupView.as_view(), name="hosts_group"),
    path("group/<int:pk>/inline/", views.HostGroupInlineView.as_view(), name="hosts_group_inline"),
]
