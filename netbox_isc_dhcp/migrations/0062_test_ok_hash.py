from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0061_disk_usage")]

    operations = [
        migrations.AddField(
            model_name="dhcpserver",
            name="test_ok_hash",
            field=models.CharField(blank=True, default="", help_text="Test server: CFG set verified here (deployed, hash OK, dhcpd ran 60 s) - production may get it.", max_length=64),
        ),
    ]
