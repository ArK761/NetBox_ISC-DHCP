from django.db import models
from django.urls import reverse


class HostConfig(models.Model):
    """Singleton: where the groups (one pair of tables per group) come from."""

    group_model = models.CharField(max_length=100, blank=True, default="", help_text="Object type of the groups, e.g. tenancy.tenantgroup.")
    group_name_field = models.CharField(max_length=100, blank=True, default="name", help_text="Field of the group object that gives the table (class) name.")
    group_conditions = models.JSONField(default=list, blank=True, help_text="Conditions [{field, values, mode include|exclude}] filtering the groups (none = all).")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host config"

    def __str__(self):
        return "Hosts"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts")


class HostGroup(models.Model):
    """One group (e.g. tenant group WorkStation): where its hosts come from. Its tables are <name>_Table and <name>_StaticTable."""

    group_model = models.CharField(max_length=100)
    group_pk = models.PositiveBigIntegerField()
    name = models.CharField(max_length=200, blank=True, default="", help_text="Table name (last seen value of the name field).")
    mac_model = models.CharField(max_length=100, blank=True, default="", help_text="Object type that holds the hosts (MAC addresses), e.g. tenancy.tenant.")
    link_field = models.CharField(max_length=100, blank=True, default="", help_text="Field of the host object that points to the group.")
    host_name_field = models.CharField(max_length=100, blank=True, default="name", help_text="Field of the host object that gives the host name.")
    mac_fields = models.JSONField(default=list, blank=True, help_text="Fields with MAC addresses (1-3), in order.")
    ip_field = models.CharField(max_length=100, blank=True, default="", help_text="Field with the static IP (empty = no static hosts).")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host group"
        constraints = [models.UniqueConstraint(fields=("group_model", "group_pk"), name="netbox_isc_dhcp_hostgroup_unique")]

    def __str__(self):
        return self.name or f"{self.group_model}#{self.group_pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts_group", kwargs={"pk": self.pk})

    def source_fields(self):
        return {"mac_model": self.mac_model, "link_field": self.link_field, "host_name_field": self.host_name_field,
                "mac_fields": list(self.mac_fields or []), "ip_field": self.ip_field}


def host_config() -> HostConfig:
    return HostConfig.objects.first() or HostConfig.objects.create()
