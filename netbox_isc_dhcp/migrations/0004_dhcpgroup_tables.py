from django.db import migrations, models

import netbox_isc_dhcp.dhcp_tables


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0003_dhcpgroup_enabled")]

    operations = [
        migrations.AddField(model_name="dhcpgroup", name="mac_fields",
            field=models.JSONField(blank=True, default=list, help_text="Tenant custom fields that hold a MAC address.")),
        migrations.AddField(model_name="dhcpgroup", name="ip_field",
            field=models.CharField(blank=True, max_length=100, help_text="Tenant custom field with the static IP (optional).")),
        migrations.AddField(model_name="dhcpgroup", name="table_template",
            field=models.TextField(blank=True, default=netbox_isc_dhcp.dhcp_tables.default_table_template, help_text="Jinja template of <Group>_Table.")),
        migrations.AddField(model_name="dhcpgroup", name="static_template",
            field=models.TextField(blank=True, default=netbox_isc_dhcp.dhcp_tables.default_static_template, help_text="Jinja template of <Group>_StaticTable.")),
    ]
