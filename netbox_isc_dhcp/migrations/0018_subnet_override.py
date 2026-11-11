import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("extras", "__latest__"), ("netbox_isc_dhcp", "0017_pool_prefix_range")]

    operations = [
        migrations.AddField(model_name="pooltemplate", name="allow_override",
            field=models.BooleanField(default=False, verbose_name="Allow individual changes")),
        migrations.CreateModel(
            name="SubnetOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder)),
                ("prefix_id", models.PositiveBigIntegerField(help_text="ipam.Prefix id")),
                ("prefix_text", models.CharField(max_length=64)),
                ("code", models.TextField(blank=True)),
                ("pool", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="overrides", to="netbox_isc_dhcp.pooltemplate")),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={"ordering": ("pool__name", "prefix_text"), "verbose_name": "individual subnet code"},
        ),
        migrations.AddConstraint(model_name="subnetoverride",
            constraint=models.UniqueConstraint(fields=("pool", "prefix_id"), name="netbox_isc_dhcp_override_unique")),
    ]
