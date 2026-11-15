from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0029_includes")]

    operations = [
        migrations.AddField(model_name="hostgroup", name="include",
                            field=models.BooleanField(default=True, help_text="Files of this group are included in dhcpd.conf (when the main switch on Hosty is on).")),
        migrations.AddField(model_name="hostconfig", name="include_each",
                            field=models.BooleanField(default=False, help_text="Control the include per group (HostGroup.include).")),
        migrations.AddField(model_name="subnetconfig", name="include_each",
                            field=models.BooleanField(default=False, help_text="Control the include per pool (PoolTemplate.include).")),
        migrations.AddField(model_name="pooltemplate", name="include",
                            field=models.BooleanField(default=True, help_text="Subnets of this pool are included in dhcpd.conf (when controlled per pool).")),
    ]
