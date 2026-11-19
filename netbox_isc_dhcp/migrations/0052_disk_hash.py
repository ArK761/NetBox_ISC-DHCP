from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0051_autosync")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="disk_hash",
                            field=models.CharField(max_length=64, blank=True, default="", help_text="ONE control hash of all CFG files on the server's disk, as the agent computes it.")),
    ]
