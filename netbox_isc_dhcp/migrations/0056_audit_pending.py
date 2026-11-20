from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0055_leases_sha")]

    operations = [
        migrations.AddField(model_name="auditevent", name="pending",
                            field=models.JSONField(default=dict, blank=True, help_text="Admin command / setting -> per server {s: wait|ok|failed, f: field, id: command id, t: done time, x: text}.")),
    ]
