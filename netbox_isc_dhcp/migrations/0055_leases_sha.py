from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0054_time_format")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="leases_sha",
                            field=models.CharField(max_length=64, blank=True, default="", help_text="sha256 of the newest lease copy, as the agent reports it.")),
    ]
