from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0039_agent_daemon")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_key",
                            field=models.CharField(max_length=64, blank=True, default="", help_text="Agent API key (Authorization: Token <key>); empty = IP check only.")),
    ]
