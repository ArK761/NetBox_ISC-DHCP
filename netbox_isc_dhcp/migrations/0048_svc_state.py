from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0047_dhcpd_pid")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="svc_state",
                            field=models.CharField(max_length=20, blank=True, default="", help_text="State of the DHCP service as the agent reports it (active, failed, inactive...).")),
        migrations.AddField(model_name="dhcpserver", name="svc_why",
                            field=models.CharField(max_length=300, blank=True, default="", help_text="Why the DHCP service is not active (unit journal), as the agent reports it.")),
    ]
