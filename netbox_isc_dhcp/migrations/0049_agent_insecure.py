from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0048_svc_state")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="agent_insecure",
                            field=models.BooleanField(default=False, help_text="The agent talks to NetBox over plain http (key and CFG unencrypted).")),
    ]
