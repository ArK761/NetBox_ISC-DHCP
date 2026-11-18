from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0045_bundle_min")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="dhcpd_why",
                            field=models.CharField(max_length=300, blank=True, default="", help_text="Why dhcpd stopped/started outside the agent (journal: command, sudo user, crash).")),
    ]
