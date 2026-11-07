import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("extras", "__latest__"),
        ("netbox_isc_dhcp", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PluginSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("last_updated", models.DateTimeField(auto_now=True, null=True)),
                (
                    "custom_field_data",
                    models.JSONField(blank=True, default=dict, encoder=utilities.json.CustomFieldJSONEncoder),
                ),
                (
                    "language",
                    models.CharField(
                        choices=[("sk", "Slovenčina"), ("en", "English")], default="sk", max_length=2
                    ),
                ),
                ("tags", taggit.managers.TaggableManager(through="extras.TaggedItem", to="extras.Tag")),
            ],
            options={"verbose_name_plural": "plugin settings"},
        ),
    ]
