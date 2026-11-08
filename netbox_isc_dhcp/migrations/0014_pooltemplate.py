import taggit.managers
import utilities.json
from django.db import migrations, models

import netbox_isc_dhcp.subnet_render


class Migration(migrations.Migration):
    dependencies = [("extras", "__latest__"), ("netbox_isc_dhcp", "0013_subnetconfig")]

    operations = [
        migrations.CreateModel(
            name="PoolTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("name", models.CharField(help_text="Pool type value, e.g. WorkStation.", max_length=100, unique=True)),
                ("enabled", models.BooleanField(default=True, verbose_name="Generate")),
                ("template", models.TextField(blank=True, default=netbox_isc_dhcp.subnet_render.default_pool_template, help_text="Jinja template of the subnet file.")),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={"ordering": ("name",), "verbose_name": "pool"},
        ),
    ]
