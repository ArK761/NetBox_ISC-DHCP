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
    src_hash = models.CharField(max_length=64, blank=True, default="", help_text="Fingerprint of the inputs; same -> not recomputed.")
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
    kind = models.CharField(max_length=10, choices=(("regen", "Generovanie"), ("download", "Stiahnutie"), ("plan", "Plán"), ("report", "Hlásenie"),
                                                    ("agent", "Agent"), ("admin", "Správca")))
    server = models.CharField(max_length=100, blank=True, default="", help_text="DHCP server name (plan / report).")
    result = models.CharField(max_length=20, blank=True, default="", help_text="Report result: ok, test_failed, rolled_back, failed.")
    output = models.TextField(blank=True, default="", help_text="Report output (dhcpd -t, errors).")
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
    order = models.PositiveSmallIntegerField(default=1, help_text="Rollout order (1 = first).")
    test_cmd = models.CharField(max_length=255, default="dhcpd -t -cf {conf}", help_text="Config test; {conf} = path of dhcpd.conf.")
    restart_cmd = models.CharField(max_length=255, default="systemctl restart isc-dhcp-server", help_text="Restart of the DHCP service.")
    backup_dir = models.CharField(max_length=255, blank=True, default="", help_text="Backup directory (empty = <base path>/bck).")
    last_hash = models.CharField(max_length=64, blank=True, default="")
    last_result = models.CharField(max_length=20, blank=True, default="")
    last_report = models.DateTimeField(null=True, blank=True)
    # agent state (sent on every contact)
    last_seen = models.DateTimeField(null=True, blank=True, help_text="Last contact of the agent.")
    agent_version = models.CharField(max_length=50, blank=True, default="")
    isc_version = models.CharField(max_length=100, blank=True, default="", help_text="ISC dhcpd version; 'none' = not installed.")
    dhcpd_running = models.BooleanField(null=True, blank=True)
    running_hash = models.CharField(max_length=64, blank=True, default="", help_text="CFG set the agent says it runs.")
    restart_req = models.CharField(max_length=20, blank=True, default="", help_text="Manual dhcpd restart asked in NetBox (id; the agent does it once).")
    disk_broken = models.CharField(max_length=64, blank=True, default="", help_text="Failed CFG kept on disk (debugging) - dhcpd would not start after a reboot.")
    key_hash = models.CharField(max_length=16, blank=True, default="", help_text="Short hash of the key the agent used last.")
    released_hash = models.CharField(max_length=64, blank=True, default="", help_text="Admin let the next servers go on without this server's OK for this set.")

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "DHCP server"
        ordering = ("order", "name")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:pluginsettings_list") + "#isc-servers"


class CfgVersion(models.Model):
    """Number of every CFG set (manifest hash): <dd.mm.yy>_<NNN> per day, e.g. 18.11.26_000."""

    hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=20)
    created = models.DateTimeField(db_index=True)

    class Meta:
        app_label = "netbox_isc_dhcp"
        verbose_name = "CFG version"
        ordering = ("-created",)

    def __str__(self):
        return self.label

    def get_absolute_url(self):
        return reverse("plugins:netbox_isc_dhcp:export")
