from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0042_keep_failed")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="restart_req",
                            field=models.CharField(max_length=20, blank=True, default="", help_text="Manual dhcpd restart asked in NetBox (id; the agent does it once).")),
    ]
