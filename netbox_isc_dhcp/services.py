"""Glue between NetBox data and the pure generators."""
import hashlib

from django.utils import timezone
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant

from .base_config import is_safe_name, render_base_config
from .dhcp_tables import FileResult, build_file
from .models import BaseConfig, DHCPFile, DHCPPath, base_path


def dhcp_prefixes(cfg: BaseConfig) -> list[str]:
    lookup = {f"custom_field_data__{cfg.prefix_field}": cfg.prefix_value}
    return [str(p) for p in Prefix.objects.filter(**lookup).values_list("prefix", flat=True)]


def _dir_path(name: str):
    d = DHCPPath.objects.filter(name=name).first()
    return d.path if d else None


def table_includes() -> tuple[list[str], list[str]]:
    """Full paths of all enabled table files in include order, plus warnings."""
    files = (
        DHCPFile.objects.filter(enabled=True, group__enabled=True)
        .select_related("group__group", "directory")
        .order_by("group__order", "group__group__name", "order", "name")
    )
    paths, warnings = [], []
    for f in files:
        if f.directory is None:
            warnings.append(f"File '{f.name}' skipped: no subdirectory chosen.")
        elif is_safe_name(f.name):
            paths.append(f.full_path)
        else:
            warnings.append(f"File '{f.name}' skipped: name contains characters not allowed in file names.")
    table = _dir_path("TABLE")
    return paths + ([f"{table}/Netbox_Devices-MAC"] if table else []), warnings


def build_base_config(cfg: BaseConfig) -> tuple[str, list[str]]:
    """Return (dhcpd.conf text, warnings)."""
    tables, warnings = table_includes()
    subnet = _dir_path("SUBNET")
    if subnet is None:
        warnings.append("No SUBNET subdirectory: prefix includes are left out.")
    text = render_base_config(cfg.static_text, tables, dhcp_prefixes(cfg) if subnet else [], subnet_dir=subnet or "")
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
