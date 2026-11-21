from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0058_first_leases")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="is_test",
                            field=models.BooleanField(default=False, help_text="Test DHCP server: first in the rollout, the Test button simulates the first run of the agent.")),
    ]
