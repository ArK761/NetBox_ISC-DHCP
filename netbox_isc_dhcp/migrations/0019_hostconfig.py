from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_isc_dhcp", "0018_subnet_override"),
    ]

    operations = [
        migrations.CreateModel(
            name="HostConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("group_model", models.CharField(blank=True, default="", help_text="Object type of the groups (DHCP classes), e.g. tenancy.tenantgroup.", max_length=100)),
                ("mac_model", models.CharField(blank=True, default="", help_text="Object type that holds the MAC addresses, e.g. tenancy.tenant.", max_length=100)),
                ("link_field", models.CharField(blank=True, default="", help_text="Field of the MAC object that points to its group.", max_length=100)),
                ("mac_fields", models.JSONField(blank=True, default=list, help_text="Fields with MAC addresses (1-3).")),
                ("ip_field", models.CharField(blank=True, default="", help_text="Field with the static IP (empty = no static hosts).", max_length=100)),
            ],
            options={"verbose_name": "host config"},
        ),
    ]
