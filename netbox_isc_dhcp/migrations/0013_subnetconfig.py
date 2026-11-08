import taggit.managers
import utilities.json
from django.db import migrations, models


def move(apps, schema_editor):
    BaseConfig = apps.get_model("netbox_isc_dhcp", "BaseConfig")
    SubnetConfig = apps.get_model("netbox_isc_dhcp", "SubnetConfig")
    b = BaseConfig.objects.first()
    SubnetConfig.objects.create(source_model=b.source_model if b else "", conditions=b.conditions if b else [])


class Migration(migrations.Migration):
    dependencies = [("extras", "__latest__"), ("netbox_isc_dhcp", "0012_source_any_object")]

    operations = [
        migrations.CreateModel(
            name="SubnetConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("name", models.CharField(default="subnets", max_length=100, unique=True)),
                ("source_model", models.CharField(blank=True, default="", help_text="Object (any NetBox object type) the subnets are taken from.", max_length=100)),
                ("conditions", models.JSONField(blank=True, default=list, help_text="Fields of the object and the accepted values (all must match).")),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={"ordering": ("name",), "verbose_name": "subnet config"},
        ),
        migrations.RunPython(move, migrations.RunPython.noop),
        migrations.RemoveField(model_name="baseconfig", name="source_model"),
        migrations.RemoveField(model_name="baseconfig", name="conditions"),
    ]
