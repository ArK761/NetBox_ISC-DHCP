from django.db import migrations, models


def copy_shared(apps, schema_editor):
    """Code edited on the old shared card (v0.17.0) -> every group."""
    HostConfig = apps.get_model("netbox_isc_dhcp", "HostConfig")
    HostGroup = apps.get_model("netbox_isc_dhcp", "HostGroup")
    cfg = HostConfig.objects.first()
    if cfg and (cfg.dynamic_code or cfg.static_code):
        HostGroup.objects.update(dynamic_code=cfg.dynamic_code, static_code=cfg.static_code)


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0025_hostconfig_code")]

    operations = [
        migrations.AddField(model_name="hostgroup", name="dynamic_code",
                            field=models.TextField(blank=True, default="", help_text="Jinja code of the _Dynamic file of this group (empty = default).")),
        migrations.AddField(model_name="hostgroup", name="static_code",
                            field=models.TextField(blank=True, default="", help_text="Jinja code of the _Static file of this group (empty = default).")),
        migrations.RunPython(copy_shared, migrations.RunPython.noop),
    ]
