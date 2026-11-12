from django.db import models
from django.urls import reverse


class HostConfig(models.Model):
    """Singleton: where DHCP classes (groups) and hosts (MAC + IP) come from."""

    group_model = models.CharField(max_length=100, blank=True, default="", help_text="Object type of the groups (DHCP classes), e.g. tenancy.tenantgroup.")
    mac_model = models.CharField(max_length=100, blank=True, default="", help_text="Object type that holds the MAC addresses, e.g. tenancy.tenant.")
    group_name_field = models.CharField(max_length=100, blank=True, default="name", help_text="Field of the group object that gives the table (class) name.")
    group_conditions = models.JSONField(default=list, blank=True, help_text="Conditions [{field, values, mode include|exclude}] choosing the groups that get tables.")
    host_name_field = models.CharField(max_length=100, blank=True, default="name", help_text="Field of the MAC object that gives the host name.")
    link_field = models.CharField(max_length=100, blank=True, default="", help_text="Field of the MAC object that points to its group.")
    mac_fields = models.JSONField(default=list, blank=True, help_text="Fields with MAC addresses (1-3).")
    ip_field = models.CharField(max_length=100, blank=True, default="", help_text="Field with the static IP (empty = no static hosts).")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host config"

    def __str__(self):
        return "Hosts"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts")


def host_config() -> HostConfig:
    return HostConfig.objects.first() or HostConfig.objects.create()
