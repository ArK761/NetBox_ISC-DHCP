from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0035_agent")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="agent_mode",
                            field=models.CharField(choices=[("plan", "Plan"), ("export", "Export")], default="plan", max_length=10,
                                                   help_text="For all DHCP servers: plan = only changes, export = download everything.")),
    ]
