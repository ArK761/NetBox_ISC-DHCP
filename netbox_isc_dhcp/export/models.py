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
