from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_isc_dhcp", "0021_hostgroup"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostgroup",
            name="enabled",
            field=models.BooleanField(default=True, help_text="Off: both files are still made, but without MAC addresses (base content only)."),
        ),
    ]
