from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0056_audit_pending")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="takeover",
                            field=models.CharField(max_length=10, blank=True, default="", help_text="Original DHCP found by the agent: '' | foreign (waiting for the admin's consent) | approved.")),
        migrations.AddField(model_name="dhcpserver", name="takeover_info",
                            field=models.CharField(max_length=1000, blank=True, default="", help_text="What the agent found: dhcpd state, include files of the original dhcpd.conf.")),
    ]
