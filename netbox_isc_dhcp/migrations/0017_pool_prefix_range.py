from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0016_configvariable")]

    operations = [
        migrations.AddField(model_name="pooltemplate", name="suitable",
            field=models.JSONField(blank=True, default=list, help_text="Prefix lengths the code works for (computed).")),
        migrations.AddField(model_name="pooltemplate", name="min_prefixlen",
            field=models.PositiveSmallIntegerField(blank=True, null=True, help_text="Use only for prefixes from /min ...")),
        migrations.AddField(model_name="pooltemplate", name="max_prefixlen",
            field=models.PositiveSmallIntegerField(blank=True, null=True, help_text="... to /max.")),
    ]
