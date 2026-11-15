from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0028_hostgroupcode")]

    operations = [
        migrations.AddField(model_name="hostconfig", name="include_tables",
                            field=models.BooleanField(default=False, help_text="Write include lines of all group files into dhcpd.conf.")),
        migrations.AddField(model_name="subnetconfig", name="include_subnets",
                            field=models.BooleanField(default=False, help_text="Write include lines of the subnet files (<network>_CFG) into dhcpd.conf.")),
    ]
