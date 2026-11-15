from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0036_agent_mode")]

    operations = [
        migrations.AddField(model_name="pluginsettings", name="staged_rollout",
                            field=models.BooleanField(default=False, help_text="Servers get a new CFG one after another (by order): the next only after the previous reported OK.")),
        migrations.AddField(model_name="dhcpserver", name="order", field=models.PositiveSmallIntegerField(default=1, help_text="Rollout order (1 = first).")),
        migrations.AlterModelOptions(name="dhcpserver", options={"verbose_name": "DHCP server", "ordering": ("order", "name")}),
    ]
