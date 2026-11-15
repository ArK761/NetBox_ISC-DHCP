from django.db import models
from django.urls import reverse


class HostConfig(models.Model):
    """Singleton: where the groups (one pair of tables per group) come from."""

    group_model = models.CharField(max_length=100, blank=True, default="", help_text="Object type of the groups, e.g. tenancy.tenantgroup.")
    group_name_field = models.CharField(max_length=100, blank=True, default="name", help_text="Field of the group object that gives the table (class) name.")
    group_conditions = models.JSONField(default=list, blank=True, help_text="Conditions [{field, values, mode include|exclude}] filtering the groups (none = all).")
    dynamic_code = models.TextField(blank=True, default="", help_text="Jinja code of every <name>_Dynamic file (empty = default).")
    static_code = models.TextField(blank=True, default="", help_text="Jinja code of every <name>_Static file (empty = default).")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host config"

    def __str__(self):
        return "Hosts"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts")

    def code(self, kind):
        from .codegen import DEFAULT_DYNAMIC, DEFAULT_STATIC
        own = self.dynamic_code if kind == "dynamic" else self.static_code
        return own or (DEFAULT_DYNAMIC if kind == "dynamic" else DEFAULT_STATIC)

    def is_default(self, kind):
        return not (self.dynamic_code if kind == "dynamic" else self.static_code)


class HostCodeTemplate(models.Model):
    """Library of file codes (Hosts page); a group picks one per file and may edit it locally."""

    KINDS = (("dynamic", "Dynamic"), ("static", "Static"))

    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=KINDS)
    code = models.TextField(blank=True, default="")

    class Meta:
        app_label = "netbox_isc_dhcp"
        ordering = ("kind", "name")
        verbose_name = "code template"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts") + f"#t{self.pk}"


class HostGroup(models.Model):
    """One group (e.g. tenant group WorkStation) = two files: <name><dynamic_suffix> and <name><static_suffix>,
    each built from its own sources (HostSource)."""

    group_model = models.CharField(max_length=100)
    group_pk = models.PositiveBigIntegerField()
    name = models.CharField(max_length=200, blank=True, default="", help_text="Table name (last seen value of the name field).")
    enabled = models.BooleanField(default=True, help_text="Off: both files are still made, but without MAC addresses (base content only).")
    dynamic_suffix = models.CharField(max_length=50, default="_Dynamic", help_text="File name = group name + this suffix (hosts without IP).")
    static_suffix = models.CharField(max_length=50, default="_Static", help_text="File name = group name + this suffix (hosts with static IP).")
    dynamic_template = models.ForeignKey(HostCodeTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    static_template = models.ForeignKey(HostCodeTemplate, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    dynamic_code = models.TextField(blank=True, default="", help_text="Unused since 0028 (moved to HostGroupCode).")
    static_code = models.TextField(blank=True, default="", help_text="Unused since 0028 (moved to HostGroupCode).")
    dynamic_local = models.ForeignKey("HostGroupCode", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    static_local = models.ForeignKey("HostGroupCode", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "host group"
        constraints = [models.UniqueConstraint(fields=("group_model", "group_pk"), name="netbox_isc_dhcp_hostgroup_unique")]

    def __str__(self):
        return self.name or f"{self.group_model}#{self.group_pk}"

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:hosts_group", kwargs={"pk": self.pk})

    def template(self, kind):
        return self.dynamic_template if kind == "dynamic" else self.static_template

    def base_code(self, kind):
        """Code of the chosen template (or the built-in default)."""
        from .codegen import DEFAULT_DYNAMIC, DEFAULT_STATIC
        tpl = self.template(kind)
        if tpl is not None and tpl.code:
            return tpl.code
        return DEFAULT_DYNAMIC if kind == "dynamic" else DEFAULT_STATIC

    def local(self, kind):
        """Own code of this group used for the file (None = the template is used)."""
        return self.dynamic_local if kind == "dynamic" else self.static_local

    def code(self, kind):
        loc = self.local(kind)
        return loc.code if loc is not None else self.base_code(kind)

    def is_default(self, kind):
        """No own code in use: the file uses its template as it is."""
        return self.local(kind) is None

    @property
    def is_default_dynamic(self):
        return self.dynamic_local_id is None

    @property
    def is_default_static(self):
        return self.static_local_id is None

    def file_name(self, kind):
        return f"{self.name}{self.dynamic_suffix if kind == 'dynamic' else self.static_suffix}"


class HostGroupCode(models.Model):
    """Own (local) code of one file of a group; a group may keep several, one of them (or a template) is used."""

    group = models.ForeignKey(HostGroup, on_delete=models.CASCADE, related_name="codes")
    kind = models.CharField(max_length=10, choices=(("dynamic", "Dynamic"), ("static", "Static")))
    name = models.CharField(max_length=100)
    code = models.TextField(blank=True, default="")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "group code"
        ordering = ("kind", "name")
        constraints = [models.UniqueConstraint(fields=("group", "kind", "name"), name="netbox_isc_dhcp_hostgroupcode_unique")]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return self.group.get_absolute_url() + f"#isc-file-{self.kind}"


class HostSource(models.Model):
    """One source of a group: objects of a type chosen by conditions. Each object gives up to 3 hosts (rows);
    a row = MAC field + optional IP field. Row with IP -> static host block (and, if `dyn`, the MAC also into the
    dynamic class); row without IP -> dynamic class only."""

    group = models.ForeignKey(HostGroup, on_delete=models.CASCADE, related_name="sources")
    order = models.PositiveSmallIntegerField(default=100)
    model = models.CharField(max_length=100, blank=True, default="", help_text="Object type of the hosts, e.g. tenancy.tenant or dcim.device.")
    conditions = models.JSONField(default=list, blank=True, help_text="Conditions [{field, values, mode include|exclude}] choosing the objects.")
    host_name_field = models.CharField(max_length=100, blank=True, default="name")
    hosts = models.JSONField(default=list, blank=True, help_text="Hosts of one object: [{mac, ip, dyn}] (max 3); every field used once.")

    class Meta:
        app_label = "netbox_isc_dhcp"
        ordering = ("group", "order", "pk")
        verbose_name = "host source"

    def __str__(self):
        return f"{self.group} {self.model}"

    def get_absolute_url(self):
        return self.group.get_absolute_url()


def host_config() -> HostConfig:
    return HostConfig.objects.first() or HostConfig.objects.create()
