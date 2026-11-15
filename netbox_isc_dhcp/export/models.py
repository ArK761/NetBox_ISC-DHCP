from django.db import models
from django.urls import reverse


class ExportFile(models.Model):
    """One generated file exactly as the DHCP server gets it. The set of rows = the set of files on the server
    (and of includes in dhcpd.conf); recomputed only where a change happened."""

    path = models.CharField(max_length=500, unique=True)
    area = models.CharField(max_length=10, choices=(("conf", "dhcpd.conf"), ("table", "TABLE"), ("subnet", "SUBNET")))
    key = models.CharField(max_length=100, unique=True, help_text="What the file is made from: conf, group:<pk>:<kind>, subnet:<prefix pk>.")
    content = models.TextField(blank=True, default="")
    sha256 = models.CharField(max_length=64)
    size = models.PositiveIntegerField(default=0)
    updated = models.DateTimeField()

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "export file"
        ordering = ("path",)

    def __str__(self):
        return self.path

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:export") + f"#f{self.pk}"


class AuditEvent(models.Model):
    """Audit log: regenerations (who/why, duration, changed files with diff) and downloads by DHCP servers."""

    time = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=10, choices=(("regen", "Generovanie"), ("download", "Stiahnutie"), ("report", "Hlásenie")))
    user = models.CharField(max_length=150, blank=True, default="")
    client_ip = models.CharField(max_length=64, blank=True, default="")
    cause = models.TextField(blank=True, default="", help_text="Why: saved objects, button, plugin update.")
    duration_ms = models.PositiveIntegerField(default=0)
    manifest_hash = models.CharField(max_length=64, blank=True, default="")
    changes = models.JSONField(default=list, blank=True, help_text="[{path, action add|update|delete, old, new, diff}] or downloaded paths.")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "audit event"
        ordering = ("-time",)

    def __str__(self):
        return f"{self.time:%Y-%m-%d %H:%M:%S} {self.kind}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:audit") + f"#a{self.pk}"


class DHCPServer(models.Model):
    """DHCP server that may download the files (address = IP or FQDN, FQDN is resolved)."""

    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, help_text="IP address or FQDN of the DHCP server.")
    enabled = models.BooleanField(default=True)

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "DHCP server"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers"
