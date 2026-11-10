import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("extras", "__latest__"), ("netbox_isc_dhcp", "0015_gateway_mode")]

    operations = [
        migrations.CreateModel(
            name="ConfigVariable",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("name", models.CharField(help_text="Description used in pool code: USE <name>.", max_length=60, unique=True)),
                ("option", models.CharField(help_text="ISC option from the catalog.", max_length=40)),
                ("value", models.TextField(blank=True)),
                ("dns_servers", models.JSONField(blank=True, default=list, help_text="DNS servers (ids) for DNS options.")),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={"ordering": ("name",), "verbose_name": "variable"},
        ),
        migrations.AddField(model_name="pluginsettings", name="lease_factor",
                            field=models.FloatField(default=1.3, help_text="max-lease-time = lease x this factor.")),
    ]
