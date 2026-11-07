from django.core.exceptions import ValidationError
from django.db import models
from netbox.models import NetBoxModel

from .base_config import default_static_text, is_safe_name, is_safe_path
from .dhcp_tables import build_file, default_table_template
from .i18n import t
from .renderer import RenderError

MAX_ACTIVE_DNS = 2
DEFAULT_BASE_PATH = "/opt/dhcp"


class BaseConfig(NetBoxModel):
    """Primary dhcpd.conf: passive text written by the user + generated include lists."""

    name = models.CharField(max_length=100, unique=True, default="dhcpd.conf")
    config_path = models.CharField(max_length=255, default="/etc/dhcp", help_text="Directory of dhcpd.conf on the DHCP server.")
    base_path = models.CharField(max_length=255, default=DEFAULT_BASE_PATH, help_text="Base directory of all other DHCP files; directories (TABLE, SUBNET...) live below it.")
    static_text = models.TextField(
        blank=True, default=default_static_text,
        help_text="Passive part of dhcpd.conf. Used as plain text, nothing in it is processed.",
    )
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

    def clean(self):
        super().clean()
        errors = {f: "Must be an absolute path without spaces, quotes or '..'." for f in ("config_path", "base_path") if not is_safe_path(getattr(self, f))}
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating:
            for order, name in ((10, "TABLE"), (20, "SUBNET")):
                DHCPPath.objects.get_or_create(name=name, defaults={"order": order})


def base_path() -> str:
    cfg = BaseConfig.objects.first()
    return (cfg.base_path if cfg else DEFAULT_BASE_PATH).rstrip("/")


class DHCPPath(NetBoxModel):
    """A directory below the base path (TABLE, SUBNET...). Files choose one."""

    name = models.CharField(max_length=50, unique=True)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ("order", "name")
        verbose_name = "directory"

    def __str__(self):
        return self.name

    @property
    def path(self) -> str:
        return f"{base_path()}/{self.name}"

    def clean(self):
        super().clean()
        if not is_safe_name(self.name):
            raise ValidationError({"name": "Only letters, digits, '_', '.', '-'."})


class DHCPGroup(NetBoxModel):
    """A tenant group that has its own table files."""

    group = models.OneToOneField("tenancy.TenantGroup", on_delete=models.CASCADE, related_name="+")
    enabled = models.BooleanField(default=True, verbose_name="Export to dhcpd.conf")
    order = models.PositiveSmallIntegerField(default=100, help_text="Order of the include lines.")

    class Meta:
        ordering = ("order", "group__name")

    def __str__(self):
        return self.group.name

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.files.exists():  # start with the two usual files, user can rename or add more
            from .dhcp_tables import default_static_template

            d, _ = DHCPPath.objects.get_or_create(name="TABLE", defaults={"order": 10})
            DHCPFile.objects.create(group=self, name=f"{self.group.name}_Table", directory=d, order=10,
                                    template=default_table_template())
            DHCPFile.objects.create(group=self, name=f"{self.group.name}_StaticTable", directory=d, order=20,
                                    template=default_static_template())


class DHCPFile(NetBoxModel):
    """One generated file of a tenant group: own name, directory, fields and parsing template."""

    group = models.ForeignKey(DHCPGroup, on_delete=models.CASCADE, related_name="files")
    name = models.CharField(max_length=100, help_text="File name, e.g. WorkStation_Table.")
    directory = models.ForeignKey(DHCPPath, on_delete=models.PROTECT, related_name="files")
    enabled = models.BooleanField(default=True, verbose_name="Include in dhcpd.conf")
    order = models.PositiveSmallIntegerField(default=100)
    mac_fields = models.JSONField(default=list, blank=True, help_text="Tenant custom fields that hold a MAC address.")
    ip_field = models.CharField(max_length=100, blank=True, help_text="Tenant custom field with the static IP (optional).")
    template = models.TextField(blank=True, default=default_table_template, help_text="Jinja template: how the file looks.")
    # Stored result: the file is generated when something changes, never when a page is opened.
    content = models.TextField(blank=True, editable=False)
    sha256 = models.CharField(max_length=64, blank=True, editable=False)
    generated = models.DateTimeField(null=True, blank=True, editable=False)
    warnings = models.JSONField(default=list, blank=True, editable=False)

    class Meta:
        ordering = ("order", "name")
        constraints = [models.UniqueConstraint(fields=("directory", "name"), name="netbox_isc_dhcp_file_unique")]

    def __str__(self):
        return self.name

    @property
    def full_path(self) -> str:
        return f"{self.directory.path}/{self.name}"

    def clean(self):
        super().clean()
        if not is_safe_name(self.name):
            raise ValidationError({"name": "Only letters, digits, '_', '.', '-'."})
        try:  # catches template syntax errors before they can reach a generated file
            build_file("Sample", [("PC1", ["AA:BB:CC:DD:EE:01"], None), ("PC2", ["AA:BB:CC:DD:EE:02", "AA:BB:CC:DD:EE:03"], "10.0.0.2")], self.template)
        except RenderError as exc:
            raise ValidationError({"template": f"Template error: {exc}"}) from exc


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
