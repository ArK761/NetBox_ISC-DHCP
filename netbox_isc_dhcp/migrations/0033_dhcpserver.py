from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0032_auditevent")]

    operations = [
        migrations.CreateModel(
            name="DHCPServer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("address", models.CharField(help_text="IP address or FQDN of the DHCP server.", max_length=255)),
                ("enabled", models.BooleanField(default=True)),
            ],
            options={"verbose_name": "DHCP server", "ordering": ("name",)},
        ),
    ]
