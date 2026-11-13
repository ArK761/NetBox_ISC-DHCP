from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0024_hostsource_hosts")]

    operations = [
        migrations.AddField(model_name="hostconfig", name="dynamic_code",
                            field=models.TextField(blank=True, default="", help_text="Jinja code of every <name>_Dynamic file (empty = default).")),
        migrations.AddField(model_name="hostconfig", name="static_code",
                            field=models.TextField(blank=True, default="", help_text="Jinja code of every <name>_Static file (empty = default).")),
    ]
