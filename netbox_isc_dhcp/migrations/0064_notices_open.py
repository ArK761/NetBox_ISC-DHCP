from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0063_test_until")]

    operations = [
        migrations.AddField(
            model_name="pluginsettings",
            name="notices_open",
            field=models.BooleanField(default=False, help_text="Warnings bar at the bottom of plugin pages: expanded (one line per warning) when a page opens."),
        ),
    ]
