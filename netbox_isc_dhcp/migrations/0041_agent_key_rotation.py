from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0040_agent_key")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_key_old",
                            field=models.CharField(max_length=64, blank=True, default="", help_text="Previous key, valid until every server uses the new one ('-' = no key was required).")),
        migrations.AddField(model_name="dhcpserver", name="key_hash",
                            field=models.CharField(max_length=16, blank=True, default="", help_text="Short hash of the key the agent used last.")),
    ]
