from django.db import migrations, models


def copy(apps, schema_editor):
    S = apps.get_model("netbox_isc_dhcp", "DHCPServer")
    P = apps.get_model("netbox_isc_dhcp", "PluginSettings")
    srv = S.objects.order_by("order", "pk").first()
    if srv:
        P.objects.update(agent_test_cmd=srv.test_cmd, agent_restart_cmd=srv.restart_cmd, agent_backup_dir=srv.backup_dir)


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0037_staged_rollout")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_test_cmd", field=models.CharField(max_length=255, default="dhcpd -t -cf {conf}", help_text="Config test for all DHCP servers; {conf} = path of dhcpd.conf.")),
        migrations.AddField(model_name="pluginsettings", name="agent_restart_cmd", field=models.CharField(max_length=255, default="systemctl restart isc-dhcp-server", help_text="Restart of the DHCP service (all servers).")),
        migrations.AddField(model_name="pluginsettings", name="agent_backup_dir", field=models.CharField(max_length=255, blank=True, default="", help_text="Backup directory for all servers (empty = <base path>/bck).")),
        migrations.RunPython(copy, migrations.RunPython.noop),
    ]
