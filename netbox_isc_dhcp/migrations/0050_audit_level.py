from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0049_agent_insecure")]

    operations = [
        migrations.AddField(model_name="auditevent", name="level",
                            field=models.CharField(max_length=8, blank=True, default="", help_text="Severity: ok (green), info (yellow), warn (red); empty = derived from kind/result.")),
    ]
