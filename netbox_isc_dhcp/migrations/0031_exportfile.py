from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0030_hostgroup_include")]

    operations = [
        migrations.CreateModel(
            name="ExportFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("path", models.CharField(max_length=500, unique=True)),
                ("area", models.CharField(choices=[("conf", "dhcpd.conf"), ("table", "TABLE"), ("subnet", "SUBNET")], max_length=10)),
                ("key", models.CharField(help_text="What the file is made from: conf, group:<pk>:<kind>, subnet:<prefix pk>.", max_length=100, unique=True)),
                ("content", models.TextField(blank=True, default="")),
                ("sha256", models.CharField(max_length=64)),
                ("size", models.PositiveIntegerField(default=0)),
                ("updated", models.DateTimeField()),
            ],
            options={"verbose_name": "export file", "ordering": ("path",)},
        ),
    ]
