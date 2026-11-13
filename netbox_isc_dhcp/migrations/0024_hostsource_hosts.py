from django.db import migrations, models


def to_rows(apps, schema_editor):
    """Old per-file source (kind + MAC fields + IP field) -> host rows [{mac, ip, dyn}]."""
    HostSource = apps.get_model("netbox_isc_dhcp", "HostSource")
    for s in HostSource.objects.all():
        macs = [m for m in s.mac_fields or [] if m][:3]
        if s.kind == "static" and s.ip_field and macs:
            rows = [{"mac": macs[0], "ip": s.ip_field, "dyn": False}]
        else:
            rows = [{"mac": m, "ip": "", "dyn": False} for m in macs]
        s.hosts = rows
        s.save(update_fields=["hosts"])


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0023_hostsource")]

    operations = [
        migrations.AddField(model_name="hostsource", name="hosts",
                            field=models.JSONField(blank=True, default=list, help_text="Hosts of one object: [{mac, ip, dyn}] (max 3); every field used once.")),
        migrations.RunPython(to_rows, migrations.RunPython.noop),
        migrations.AlterModelOptions(name="hostsource", options={"verbose_name": "host source", "ordering": ("group", "order", "pk")}),
        migrations.RemoveField(model_name="hostsource", name="kind"),
        migrations.RemoveField(model_name="hostsource", name="mac_fields"),
        migrations.RemoveField(model_name="hostsource", name="ip_field"),
    ]
