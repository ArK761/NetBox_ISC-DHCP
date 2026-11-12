from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_isc_dhcp", "0019_hostconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="hostconfig",
            name="group_name_field",
            field=models.CharField(blank=True, default="name", help_text="Field of the group object that gives the table (class) name.", max_length=100),
        ),
        migrations.AddField(
            model_name="hostconfig",
            name="group_conditions",
            field=models.JSONField(blank=True, default=list, help_text="Conditions [{field, values, mode include|exclude}] choosing the groups that get tables."),
        ),
        migrations.AddField(
            model_name="hostconfig",
            name="host_name_field",
            field=models.CharField(blank=True, default="name", help_text="Field of the MAC object that gives the host name.", max_length=100),
        ),
    ]
