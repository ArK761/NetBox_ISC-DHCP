from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0064_notices_open")]

    operations = [
        migrations.AddField(
            model_name="pooltemplate",
            name="ref",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64,
                                   help_text="Value of the pool type field (object id) this pool belongs to - a renamed object keeps its pool and code."),
        ),
    ]
