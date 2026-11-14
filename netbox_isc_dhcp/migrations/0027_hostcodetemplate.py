import django.db.models.deletion
from django.db import migrations, models

DYN = '''class "{{ class_name }}" {
       match hardware;
                         }
{% for p in pairs %}
subclass "{{ class_name }}" 1:{{ p.mac }}; ## {{ p.host }} ##
{% endfor %}
'''

STA = '''{% for h in hosts %}
host {{ h.host }} {
      hardware ethernet {{ h.mac }};
      fixed-address {{ h.ip }};
{% if h.hostname %}
      option host-name {{ h.hostname }};
{% endif %}
        }
{% endfor %}
'''


def seed(apps, schema_editor):
    T = apps.get_model("netbox_isc_dhcp", "HostCodeTemplate")
    G = apps.get_model("netbox_isc_dhcp", "HostGroup")
    d = T.objects.create(name="Dynamic – subclass (match hardware)", kind="dynamic", code=DYN)
    s = T.objects.create(name="Static – host bloky", kind="static", code=STA)
    G.objects.update(dynamic_template=d, static_template=s)  # local code (if edited) stays as a local change


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0026_hostgroup_code")]

    operations = [
        migrations.CreateModel(
            name="HostCodeTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("kind", models.CharField(choices=[("dynamic", "Dynamic"), ("static", "Static")], max_length=10)),
                ("code", models.TextField(blank=True, default="")),
            ],
            options={"verbose_name": "code template", "ordering": ("kind", "name")},
        ),
        migrations.AddField(model_name="hostgroup", name="dynamic_template",
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.hostcodetemplate")),
        migrations.AddField(model_name="hostgroup", name="static_template",
                            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="netbox_isc_dhcp.hostcodetemplate")),
        migrations.RunPython(seed, migrations.RunPython.noop),
    ]
