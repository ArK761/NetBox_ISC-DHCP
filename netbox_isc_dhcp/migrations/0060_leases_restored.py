from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0059_is_test")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="leases_restored",
                            field=models.CharField(max_length=400, blank=True, default="", help_text="Original leases put back by the agent (unix time|text).")),
    ]
