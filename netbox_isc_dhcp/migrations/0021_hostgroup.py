from django.db import migrations, models


class Migration(migrations.Migration):
    """Host source (object, MAC/IP fields) moves from the global hosts config to every group."""

    dependencies = [
        ("netbox_isc_dhcp", "0020_hostconfig_names_groups"),
    ]

    operations = [
        migrations.RemoveField(model_name="hostconfig", name="mac_model"),
        migrations.RemoveField(model_name="hostconfig", name="link_field"),
        migrations.RemoveField(model_name="hostconfig", name="host_name_field"),
        migrations.RemoveField(model_name="hostconfig", name="mac_fields"),
        migrations.RemoveField(model_name="hostconfig", name="ip_field"),
        migrations.AlterField(
            model_name="hostconfig",
            name="group_model",
            field=models.CharField(blank=True, default="", help_text="Object type of the groups, e.g. tenancy.tenantgroup.", max_length=100),
        ),
        migrations.AlterField(
            model_name="hostconfig",
            name="group_conditions",
            field=models.JSONField(blank=True, default=list, help_text="Conditions [{field, values, mode include|exclude}] filtering the groups (none = all)."),
        ),
        migrations.CreateModel(
            name="HostGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("group_model", models.CharField(max_length=100)),
                ("group_pk", models.PositiveBigIntegerField()),
                ("name", models.CharField(blank=True, default="", help_text="Table name (last seen value of the name field).", max_length=200)),
                ("mac_model", models.CharField(blank=True, default="", help_text="Object type that holds the hosts (MAC addresses), e.g. tenancy.tenant.", max_length=100)),
                ("link_field", models.CharField(blank=True, default="", help_text="Field of the host object that points to the group.", max_length=100)),
                ("host_name_field", models.CharField(blank=True, default="name", help_text="Field of the host object that gives the host name.", max_length=100)),
                ("mac_fields", models.JSONField(blank=True, default=list, help_text="Fields with MAC addresses (1-3), in order.")),
                ("ip_field", models.CharField(blank=True, default="", help_text="Field with the static IP (empty = no static hosts).", max_length=100)),
            ],
            options={"verbose_name": "host group"},
        ),
        migrations.AddConstraint(
            model_name="hostgroup",
            constraint=models.UniqueConstraint(fields=("group_model", "group_pk"), name="netbox_isc_dhcp_hostgroup_unique"),
        ),
    ]
