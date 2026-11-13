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
    """One group (e.g. tenant group WorkStation) = two files: <name><dynamic_suffix> and <name><static_suffix>,
    each built from its own sources (HostSource)."""

    group_model = models.CharField(max_length=100)
    group_pk = models.PositiveBigIntegerField()
    name = models.CharField(max_length=200, blank=True, default="", help_text="Table name (last seen value of the name field).")
    enabled = models.BooleanField(default=True, help_text="Off: both files are still made, but without MAC addresses (base content only).")
    dynamic_suffix = models.CharField(max_length=50, default="_Dynamic", help_text="File name = group name + this suffix (hosts without IP).")
    static_suffix = models.CharField(max_length=50, default="_Static", help_text="File name = group name + this suffix (hosts with static IP).")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host group"
        constraints = [models.UniqueConstraint(fields=("group_model", "group_pk"), name="netbox_isc_dhcp_hostgroup_unique")]

    def __str__(self):
        return self.name or f"{self.group_model}#{self.group_pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts_group", kwargs={"pk": self.pk})

    def file_name(self, kind):
        return f"{self.name}{self.dynamic_suffix if kind == 'dynamic' else self.static_suffix}"


class HostSource(models.Model):
    """One source of a group file: objects of a type chosen by conditions, with their MAC fields (and IP for the static file)."""

    KINDS = (("dynamic", "dynamic"), ("static", "static"))

    group = models.ForeignKey(HostGroup, on_delete=models.CASCADE, related_name="sources")
    kind = models.CharField(max_length=10, choices=KINDS)
    order = models.PositiveSmallIntegerField(default=100)
    model = models.CharField(max_length=100, blank=True, default="", help_text="Object type of the hosts, e.g. tenancy.tenant or dcim.device.")
    conditions = models.JSONField(default=list, blank=True, help_text="Conditions [{field, values, mode include|exclude}] choosing the objects.")
    host_name_field = models.CharField(max_length=100, blank=True, default="name")
    mac_fields = models.JSONField(default=list, blank=True, help_text="Fields with MAC addresses (1-3), in order.")
    ip_field = models.CharField(max_length=100, blank=True, default="", help_text="Static file: field with the static IP. Dynamic file: objects with a value in this field are left out.")

    class Meta:
        app_label = "netbox_isc_dhcp"
        ordering = ("group", "kind", "order", "pk")
        verbose_name = "host source"

    def __str__(self):
        return f"{self.group} {self.kind} {self.model}"

    def get_absolute_url(self):
        return self.group.get_absolute_url()

    def copy_fields(self):
        return {"kind": self.kind, "order": self.order, "model": self.model, "conditions": list(self.conditions or []),
                "host_name_field": self.host_name_field, "mac_fields": list(self.mac_fields or []), "ip_field": self.ip_field}


def host_config() -> HostConfig:
    return HostConfig.objects.first() or HostConfig.objects.create()
