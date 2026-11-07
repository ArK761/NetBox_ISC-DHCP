from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0011_source_conditions")]

    operations = [
        migrations.AlterField(model_name="baseconfig", name="source_model",
            field=models.CharField(blank=True, default="", help_text="Object (any NetBox object type) the config is built from.", max_length=100)),
    ]
