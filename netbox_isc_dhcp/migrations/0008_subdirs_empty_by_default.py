import django.db.models.deletion
from django.db import migrations, models


def remove_default_subdirs(apps, schema_editor):
    """Subdirectories are empty by default: drop the TABLE/SUBNET ones created automatically before."""
    DHCPPath = apps.get_model("netbox_isc_dhcp", "DHCPPath")
    DHCPFile = apps.get_model("netbox_isc_dhcp", "DHCPFile")
    auto = DHCPPath.objects.filter(name__in=("TABLE", "SUBNET"))
    DHCPFile.objects.filter(directory__in=auto).update(directory=None)
    auto.delete()


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0007_paths_in_settings")]

    operations = [
        migrations.AlterField(
            model_name="dhcpfile", name="directory",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="files", to="netbox_isc_dhcp.dhcppath"),
        ),
        migrations.RunPython(remove_default_subdirs, migrations.RunPython.noop),
    ]
