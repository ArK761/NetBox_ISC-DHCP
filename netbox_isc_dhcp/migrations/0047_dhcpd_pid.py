from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0046_dhcpd_why")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="dhcpd_pid",
                            field=models.CharField(max_length=10, blank=True, default="", help_text="PID of the running dhcpd process, as the agent reports it.")),
    ]
