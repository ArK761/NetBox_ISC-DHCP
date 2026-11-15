from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("netbox_isc_dhcp", "0031_exportfile")]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("time", models.DateTimeField(db_index=True)),
                ("kind", models.CharField(choices=[("regen", "Generovanie"), ("download", "Stiahnutie"), ("report", "Hlásenie")], max_length=10)),
                ("user", models.CharField(blank=True, default="", max_length=150)),
                ("client_ip", models.CharField(blank=True, default="", max_length=64)),
                ("cause", models.TextField(blank=True, default="", help_text="Why: saved objects, button, plugin update.")),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("manifest_hash", models.CharField(blank=True, default="", max_length=64)),
                ("changes", models.JSONField(blank=True, default=list, help_text="[{path, action add|update|delete, old, new, diff}] or downloaded paths.")),
            ],
            options={"verbose_name": "audit event", "ordering": ("-time",)},
        ),
    ]
