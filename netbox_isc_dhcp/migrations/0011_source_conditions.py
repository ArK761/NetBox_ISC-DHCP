from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0010_default_dirs_source")]

    operations = [
        migrations.AlterField(model_name="baseconfig", name="source_model",
            field=models.CharField(blank=True, choices=[("ipam.prefix", "IPAM › Prefix")], default="", help_text="Object the subnet includes are built from.", max_length=50)),
        migrations.AddField(model_name="baseconfig", name="conditions",
            field=models.JSONField(blank=True, default=list, help_text="Fields of the object and the accepted values (all must match).")),
        migrations.RunSQL("UPDATE netbox_isc_dhcp_baseconfig SET source_model = ''", migrations.RunSQL.noop),
        migrations.RemoveField(model_name="baseconfig", name="prefix_field"),
        migrations.RemoveField(model_name="baseconfig", name="prefix_value"),
    ]
