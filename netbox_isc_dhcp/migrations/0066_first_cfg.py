from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0065_pool_ref")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="first_cfg",
                            field=models.CharField(max_length=1000, blank=True, default="", help_text="Agent's backup of the original CFG (start_<time>): path|files|KB, comma separated.")),
    ]
