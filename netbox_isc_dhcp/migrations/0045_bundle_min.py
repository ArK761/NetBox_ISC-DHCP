from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0044_agent_cmd")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_bundle_min",
                            field=models.PositiveIntegerField(default=10, help_text="The agent downloads one tar.gz bundle from this many changed files on; fewer = file by file.")),
    ]
