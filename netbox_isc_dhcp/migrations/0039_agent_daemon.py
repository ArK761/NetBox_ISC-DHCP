from django.db import migrations, models


def fixed_conf(apps, schema_editor):
    P = apps.get_model("netbox_isc_dhcp", "PluginSettings")
    P.objects.update(config_path="/etc/dhcp")


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0038_agent_cmds_shared")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_interval",
                            field=models.PositiveIntegerField(default=60, help_text="Seconds between two agent contacts (10 s - 30 min).")),
        migrations.AddField(model_name="pluginsettings", name="agent_dirs",
                            field=models.JSONField(default=list, blank=True, help_text="Every directory the plugin ever managed (old files there are deleted).")),
        migrations.AddField(model_name="dhcpserver", name="last_seen", field=models.DateTimeField(null=True, blank=True, help_text="Last contact of the agent.")),
        migrations.AddField(model_name="dhcpserver", name="agent_version", field=models.CharField(max_length=50, blank=True, default="")),
        migrations.AddField(model_name="dhcpserver", name="isc_version", field=models.CharField(max_length=100, blank=True, default="", help_text="ISC dhcpd version; 'none' = not installed.")),
        migrations.AddField(model_name="dhcpserver", name="dhcpd_running", field=models.BooleanField(null=True, blank=True)),
        migrations.AddField(model_name="dhcpserver", name="running_hash", field=models.CharField(max_length=64, blank=True, default="", help_text="CFG set the agent says it runs.")),
        migrations.AddField(model_name="dhcpserver", name="released_hash", field=models.CharField(max_length=64, blank=True, default="", help_text="Admin let the next servers go on without this server's OK for this set.")),
        migrations.AlterField(model_name="auditevent", name="kind", field=models.CharField(max_length=10, choices=(("regen", "Generovanie"), ("download", "Stiahnutie"), ("plan", "Plán"), ("report", "Hlásenie"), ("agent", "Agent"), ("admin", "Správca")))),
        migrations.CreateModel(name="CfgVersion", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
            ("hash", models.CharField(max_length=64, unique=True)),
            ("label", models.CharField(max_length=20)),
            ("created", models.DateTimeField(db_index=True)),
        ], options={"verbose_name": "CFG version", "ordering": ("-created",)}),
        migrations.RunPython(fixed_conf, migrations.RunPython.noop),
    ]
