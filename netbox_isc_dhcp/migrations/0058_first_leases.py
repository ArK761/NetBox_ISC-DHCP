from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0057_takeover")]

    operations = [
        migrations.AddField(model_name="dhcpserver", name="first_leases",
                            field=models.CharField(max_length=400, blank=True, default="", help_text="First run of the agent: copy of the original leases (unix time|IPs|sha256|path).")),
        migrations.AddField(model_name="dhcpserver", name="leases_kept",
                            field=models.CharField(max_length=400, blank=True, default="", help_text="First NetBox CFG: IPs in the leases before|after the start|copy path.")),
    ]
