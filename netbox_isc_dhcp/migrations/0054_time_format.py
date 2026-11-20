from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0053_leases_copy")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_time_format",
                            field=models.CharField(max_length=10, default="eu", help_text="Date/time format of the lease copy directories on the servers: eu | iso | compact.")),
    ]
