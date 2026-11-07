import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

import netbox_isc_dhcp.base_config


def _common():
    return [
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        ("last_updated", models.DateTimeField(auto_now=True, null=True)),
        (
            "custom_field_data",
            models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
        ),
    ]


def _tags():
    return (
        "tags",
        taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag"),
    )


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("extras", "__latest__"),
        ("tenancy", "__latest__"),
    ]

    operations = [
        migrations.CreateModel(
            name="BaseConfig",
            fields=_common()
            + [
                ("name", models.CharField(default="dhcpd.conf", max_length=100, unique=True)),
                (
                    "static_text",
                    models.TextField(blank=True, default=netbox_isc_dhcp.base_config.default_static_text),
                ),
                ("table_dir", models.CharField(default="/opt/dhcp/TABLE", max_length=255)),
                ("subnet_dir", models.CharField(default="/opt/dhcp/SUBNET", max_length=255)),
                ("prefix_field", models.CharField(default="DHCP_POOL", max_length=100)),
                ("prefix_value", models.CharField(default="YES", max_length=100)),
                _tags(),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="DNSServer",
            fields=_common()
            + [
                ("name", models.CharField(max_length=100, unique=True)),
                ("ip", models.GenericIPAddressField(protocol="IPv4", verbose_name="IP")),
                ("active", models.BooleanField(default=False, verbose_name="In use")),
                _tags(),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="DHCPGroup",
            fields=_common()
            + [
                ("order", models.PositiveSmallIntegerField(default=100)),
                (
                    "group",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to="tenancy.tenantgroup",
                    ),
                ),
                _tags(),
            ],
            options={"ordering": ("order", "group__name")},
        ),
    ]
