from django.core.exceptions import ValidationError
from django.db import models
from netbox.models import NetBoxModel

from .base_config import default_static_text, is_safe_name, is_safe_path
from .dhcp_tables import build_file, default_table_template
from .i18n import t
from .renderer import RenderError
from .subnet_render import default_pool_template

MAX_ACTIVE_DNS = 2
_TEXT_FIELDS = ("static_text", "template", "value")


def _normalize_text_fields(obj):
    """Store code/text with LF line ends (browsers send CRLF)."""
    from .variables import normalize

    for f in _TEXT_FIELDS:
        if isinstance(getattr(obj, f, None), str):
            setattr(obj, f, normalize(getattr(obj, f)))
DEFAULT_BASE_PATH = "/opt/dhcp"


class BaseConfig(NetBoxModel):
    """Primary dhcpd.conf: passive text written by the user + generated include lists."""

    name = models.CharField(max_length=100, unique=True, default="dhcpd.conf")
    static_text = models.TextField(
        blank=True, default=default_static_text,
        help_text="Passive part of dhcpd.conf. Used as plain text, nothing in it is processed.",
    )
    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name



def settings_obj():
    return PluginSettings.objects.select_related("table_dir", "subnet_dir").first()


def base_path() -> str:
    cfg = PluginSettings.objects.first()
    return (cfg.base_path if cfg else "").rstrip("/")


class SubnetConfig(NetBoxModel):
    """Subnets: the object they are taken from and the conditions (any field + accepted value, all must match)."""

    name = models.CharField(max_length=100, unique=True, default="subnets")
    source_model = models.CharField(max_length=100, blank=True, default="", help_text="Object (any NetBox object type) the subnets are taken from.")
    conditions = models.JSONField(default=list, blank=True, help_text="Fields of the object and the accepted values (all must match).")
    gateway_mode = models.CharField(max_length=10, default="first", choices=(("first", "First usable IP"), ("last", "Last usable IP")),
                                    help_text="Gateway of every subnet (global).")

    class Meta:
        ordering = ("name",)
        verbose_name = "subnet config"

    def __str__(self):
        return "Subnety"


class PoolTemplate(NetBoxModel):
    """Template (script) of one pool type: how <network>_CFG of every subnet of that type looks."""

    name = models.CharField(max_length=100, unique=True, help_text="Pool type value, e.g. WorkStation.")
    enabled = models.BooleanField(default=True, verbose_name="Generate")
    template = models.TextField(blank=True, default=default_pool_template, help_text="Jinja template of the subnet file.")
    suitable = models.JSONField(default=list, blank=True, help_text="Prefix lengths the code works for (computed).")
    min_prefixlen = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Use only for prefixes from /min ...")
    max_prefixlen = models.PositiveSmallIntegerField(null=True, blank=True, help_text="... to /max.")

    class Meta:
        ordering = ("name",)
        verbose_name = "pool"

    def allowed_range(self):
        """(min, max) prefix length this pool is used for; defaults to the suitable range."""
        lo = self.min_prefixlen or (min(self.suitable) if self.suitable else None)
        hi = self.max_prefixlen or (max(self.suitable) if self.suitable else None)
        return lo, hi

    def __str__(self):
        return self.name


class ConfigVariable(NetBoxModel):
    """Own variable: a named piece of ISC config (from the option catalog). Used in pool code as `USE <name>`."""

    name = models.CharField(max_length=60, unique=True, help_text="Description used in pool code: USE <name>.")
    option = models.CharField(max_length=40, help_text="ISC option from the catalog.")
    value = models.TextField(blank=True)
    dns_servers = models.JSONField(default=list, blank=True, help_text="DNS servers (ids) for DNS options.")

    class Meta:
        ordering = ("name",)
        verbose_name = "variable"

    def __str__(self):
        return self.name

    def lines(self) -> str:
        """ISC lines of this variable (raises VariableError when the value is not valid yet)."""
        from .variables import build_lines

        order = {pk: i for i, pk in enumerate(self.dns_servers or [])}
        ips = [ip for _, ip in sorted(DNSServer.objects.filter(pk__in=self.dns_servers or []).values_list("pk", "ip"), key=lambda r: order.get(r[0], 0))]
        st = PluginSettings.objects.first()
        return build_lines(self.option, self.value, ips, st.lease_factor if st else 1.3)


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

            d = DHCPPath.objects.filter(name="TABLE").first()  # no directory yet -> user picks it later
            DHCPFile.objects.create(group=self, name=f"{self.group.name}_Table", directory=d, order=10,
                                    template=default_table_template())
            DHCPFile.objects.create(group=self, name=f"{self.group.name}_StaticTable", directory=d, order=20,
                                    template=default_static_template())


class DHCPFile(NetBoxModel):
    """One generated file of a tenant group: own name, directory, fields and parsing template."""

    group = models.ForeignKey(DHCPGroup, on_delete=models.CASCADE, related_name="files")
    name = models.CharField(max_length=100, help_text="File name, e.g. WorkStation_Table.")
    directory = models.ForeignKey(DHCPPath, on_delete=models.PROTECT, null=True, blank=True, related_name="files")
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
    def effective_directory(self):
        """Own subdirectory, otherwise the default one from plugin settings."""
        if self.directory_id:
            return self.directory
        st = settings_obj()
        return st.table_dir if st else None

    @property
    def full_path(self) -> str:
        d = self.effective_directory
        return f"{d.path}/{self.name}" if d else self.name

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
    lease_factor = models.FloatField(default=1.3, help_text="max-lease-time = lease x this factor.")
    config_path = models.CharField(max_length=255, blank=True, default="", help_text="Directory of dhcpd.conf on the DHCP server.")
    base_path = models.CharField(max_length=255, blank=True, default="", help_text="Base directory of all other DHCP files; subdirectories (TABLE, SUBNET...) live below it.")
    table_dir = models.ForeignKey("DHCPPath", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                  help_text="Default subdirectory of tenant table files.")
    subnet_dir = models.ForeignKey("DHCPPath", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   help_text="Subdirectory of the subnet (prefix) files.")

    class Meta:
        verbose_name_plural = "plugin settings"

    def __str__(self):
        return "Plugin settings"

    def clean(self):
        super().clean()
        errors = {f: "Must be an absolute path without spaces, quotes or '..'." for f in ("config_path", "base_path") if getattr(self, f) and not is_safe_path(getattr(self, f))}
        if errors:
            raise ValidationError(errors)


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
