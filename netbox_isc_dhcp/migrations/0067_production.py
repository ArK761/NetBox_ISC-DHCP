from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0066_first_cfg")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="production",
                            field=models.BooleanField(default=False, help_text="Production server (protection): NetBox never sends Stop and it cannot become the test server.")),
    ]
