from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0033_dhcpserver")]

    operations = [
        migrations.AddField(model_name="exportfile", name="src_hash",
                            field=models.CharField(blank=True, default="", help_text="Fingerprint of the inputs; same -> not recomputed.", max_length=64)),
    ]
