from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0002_pluginsettings")]

    operations = [
        migrations.AddField(
            model_name="dhcpgroup",
            name="enabled",
            field=models.BooleanField(default=True, verbose_name="Export to dhcpd.conf"),
        ),
    ]
