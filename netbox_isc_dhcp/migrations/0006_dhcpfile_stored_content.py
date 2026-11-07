from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0005_paths_and_files")]

    operations = [
        migrations.AddField(model_name="dhcpfile", name="content", field=models.TextField(blank=True, editable=False)),
        migrations.AddField(model_name="dhcpfile", name="sha256", field=models.CharField(blank=True, editable=False, max_length=64)),
        migrations.AddField(model_name="dhcpfile", name="generated", field=models.DateTimeField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name="dhcpfile", name="warnings", field=models.JSONField(blank=True, default=list, editable=False)),
    ]
