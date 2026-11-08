from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0014_pooltemplate")]

    operations = [
        migrations.AddField(model_name="subnetconfig", name="gateway_mode",
            field=models.CharField(choices=[("first", "First usable IP"), ("last", "Last usable IP")], default="first", help_text="Gateway of every subnet (global).", max_length=10)),
    ]
