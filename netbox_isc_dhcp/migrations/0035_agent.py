from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0034_exportfile_src_hash")]

    operations = [
        migrations.AlterField(model_name="auditevent", name="kind",
                              field=models.CharField(choices=[("regen", "Generovanie"), ("download", "Stiahnutie"), ("plan", "Plán"), ("report", "Hlásenie")], max_length=10)),
        migrations.AddField(model_name="auditevent", name="server", field=models.CharField(blank=True, default="", help_text="DHCP server name (plan / report).", max_length=100)),
        migrations.AddField(model_name="auditevent", name="result", field=models.CharField(blank=True, default="", help_text="Report result: ok, test_failed, rolled_back, failed.", max_length=20)),
        migrations.AddField(model_name="auditevent", name="output", field=models.TextField(blank=True, default="", help_text="Report output (dhcpd -t, errors).")),
        migrations.AddField(model_name="dhcpserver", name="test_cmd", field=models.CharField(default="dhcpd -t -cf {conf}", help_text="Config test; {conf} = path of dhcpd.conf.", max_length=255)),
        migrations.AddField(model_name="dhcpserver", name="restart_cmd", field=models.CharField(default="systemctl restart isc-dhcp-server", help_text="Restart of the DHCP service.", max_length=255)),
        migrations.AddField(model_name="dhcpserver", name="backup_dir", field=models.CharField(blank=True, default="", help_text="Backup directory (empty = <base path>/bck).", max_length=255)),
        migrations.AddField(model_name="dhcpserver", name="last_hash", field=models.CharField(blank=True, default="", max_length=64)),
        migrations.AddField(model_name="dhcpserver", name="last_result", field=models.CharField(blank=True, default="", max_length=20)),
        migrations.AddField(model_name="dhcpserver", name="last_report", field=models.DateTimeField(blank=True, null=True)),
    ]
