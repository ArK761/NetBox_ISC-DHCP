from django.core.exceptions import ValidationError
from django.db import models
from netbox.models import NetBoxModel

from .base_config import default_static_text
from .i18n import t

MAX_ACTIVE_DNS = 2


class BaseConfig(NetBoxModel):
    """Primary dhcpd.conf: passive text written by the user + generated include lists."""

    name = models.CharField(max_length=100, unique=True, default="dhcpd.conf")
    static_text = models.TextField(
        blank=True, default=default_static_text,
        help_text="Passive part of dhcpd.conf. Used as plain text, nothing in it is processed.",
    )
    table_dir = models.CharField(max_length=255, default="/opt/dhcp/TABLE")
    subnet_dir = models.CharField(max_length=255, default="/opt/dhcp/SUBNET")
    prefix_field = models.CharField(
        max_length=100, default="DHCP_POOL",
        help_text="Name of the prefix custom field that switches a prefix on.",
    )
    prefix_value = models.CharField(
        max_length=100, default="YES",
        help_text="Value of that custom field for which the prefix gets an include.",
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class DHCPGroup(NetBoxModel):
    """A tenant group that gets <Group>_Table and <Group>_StaticTable files."""

    group = models.OneToOneField("tenancy.TenantGroup", on_delete=models.CASCADE, related_name="+")
    enabled = models.BooleanField(default=True, verbose_name="Export to dhcpd.conf")
    order = models.PositiveSmallIntegerField(default=100, help_text="Order of the include lines.")

    class Meta:
        ordering = ("order", "group__name")

    def __str__(self):
        return self.group.name


class PluginSettings(NetBoxModel):
    """Global plugin settings (single row)."""

    language = models.CharField(max_length=2, default="sk", choices=(("sk", "Slovenčina"), ("en", "English")))

    class Meta:
        verbose_name_plural = "plugin settings"

    def __str__(self):
        return "Plugin settings"


class DNSServer(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    ip = models.GenericIPAddressField(protocol="IPv4", verbose_name="IP")
    active = models.BooleanField(default=False, verbose_name="In use")

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if self.active:
            others = DNSServer.objects.filter(active=True).exclude(pk=self.pk).count()
            if others >= MAX_ACTIVE_DNS:
                raise ValidationError({"active": t("err.max_dns", n=MAX_ACTIVE_DNS)})
