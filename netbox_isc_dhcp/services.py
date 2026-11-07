"""Glue between NetBox data and the pure generators."""
import hashlib

from django.utils import timezone
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant

from .base_config import is_safe_name, render_base_config
from .dhcp_tables import FileResult, build_file
from extras.models import CustomField

from .i18n import t
from .models import BaseConfig, DHCPFile, base_path, settings_obj


def dhcp_prefixes(cfg: BaseConfig) -> list[str]:
    value = cfg.prefix_value
    cf = next((c for c in CustomField.objects.get_for_model(Prefix) if c.name == cfg.prefix_field), None)
    if cf is not None and cf.type == "boolean":
        value = str(value).strip().lower() in ("1", "true", "yes", "ano", "áno")
    lookup = {f"custom_field_data__{cfg.prefix_field}": value}
    return [str(p) for p in Prefix.objects.filter(**lookup).values_list("prefix", flat=True)]


def table_includes() -> tuple[list[str], list[str]]:
    """Full paths of all enabled table files in include order, plus (at most a few, short) warnings."""
    st = settings_obj()
    files = (
        DHCPFile.objects.filter(enabled=True, group__enabled=True)
        .select_related("group__group", "directory")
        .order_by("group__order", "group__group__name", "order", "name")
    )
    paths, no_dir, bad = [], [], []
    for f in files:
        d = f.directory or (st.table_dir if st else None)
        if d is None:
            no_dir.append(f.name)
        elif not is_safe_name(f.name):
            bad.append(f.name)
        else:
            paths.append(f"{d.path}/{f.name}")
    warnings = []
    if no_dir:
        warnings.append(t("warn.no_table_dir", n=len(no_dir)))
    if bad:
        warnings.append(t("warn.bad_names", names=", ".join(bad)))
    if st and st.table_dir:
        paths.append(f"{st.table_dir.path}/Netbox_Devices-MAC")
    return paths, warnings


def build_base_config(cfg: BaseConfig) -> tuple[str, list[str]]:
    """Return (dhcpd.conf text, warnings)."""
    st = settings_obj()
    tables, warnings = table_includes()
    if not base_path():
        warnings.insert(0, t("warn.no_base_path"))
    # Subnet files (<network>_CFG) are not generated yet (no pool templates), so no subnet includes:
    # including a file nobody creates would break dhcpd.
    text = render_base_config(cfg.static_text, tables, [], subnet_dir="")
    return text, warnings


def _ip_value(value):
    """IP custom field: text value, or the pk of an IP address object."""
    if isinstance(value, int):
        obj = IPAddress.objects.filter(pk=value).first()
        return str(obj.address.ip) if obj else None
    return value


def file_content(f: DHCPFile) -> FileResult:
    """Generate one file from the tenants of its group."""
    raw = []
    for t in Tenant.objects.filter(group=f.group.group):
        cf = t.custom_field_data or {}
        ip = _ip_value(cf.get(f.ip_field)) if f.ip_field else None
        raw.append((t.name, [cf.get(m) for m in f.mac_fields], ip))
    return build_file(f.group.group.name, raw, f.template)


def regenerate_file(f: DHCPFile) -> bool:
    """Generate the file and store it. Returns True when the content changed (new hash)."""
    res = file_content(f)
    sha = hashlib.sha256(res.text.encode("utf-8")).hexdigest()
    changed = sha != f.sha256
    values = {"content": res.text, "sha256": sha, "warnings": res.warnings}
    if changed or f.generated is None:
        values["generated"] = timezone.now()
    DHCPFile.objects.filter(pk=f.pk).update(**values)  # update(): no signals, no loops
    for k, v in values.items():
        setattr(f, k, v)
    return changed
