from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0062_test_ok_hash")]

    operations = [
        migrations.AddField(
            model_name="dhcpserver",
            name="test_until",
            field=models.DateTimeField(blank=True, help_text="Test server: dhcpd started from NetBox runs until this time, then NetBox stops it.", null=True),
        ),
        migrations.AddField(
            model_name="dhcpserver",
            name="stop_why",
            field=models.CharField(blank=True, default="", help_text="Why NetBox stops dhcpd (shown in the Audit with the stop).", max_length=200),
        ),
    ]
