from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0060_leases_restored")]

    operations = [
        migrations.AddField(
            model_name="dhcpserver",
            name="disk_usage",
            field=models.CharField(blank=True, default="", help_text="Disk usage of the file systems the agent writes to (mount:percent,...).", max_length=400),
        ),
    ]
