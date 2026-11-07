"""Glue between NetBox data and the pure generators."""
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant

from .base_config import render_base_config, split_groups
from .dhcp_tables import build_group_files
from .models import BaseConfig, DHCPGroup


def dhcp_prefixes(cfg: BaseConfig) -> list[str]:
    lookup = {f"custom_field_data__{cfg.prefix_field}": cfg.prefix_value}
    return [str(p) for p in Prefix.objects.filter(**lookup).values_list("prefix", flat=True)]


def dhcp_group_names() -> list[str]:
    return [g.group.name for g in DHCPGroup.objects.filter(enabled=True).select_related("group")]


def build_base_config(cfg: BaseConfig) -> tuple[str, list[str]]:
    """Return (dhcpd.conf text, warnings)."""
    names = dhcp_group_names()
    _, rejected = split_groups(names)
    warnings = [f"Group '{n}' skipped: name contains characters not allowed in file names." for n in rejected]
    text = render_base_config(
        cfg.static_text, names, dhcp_prefixes(cfg), table_dir=cfg.table_dir, subnet_dir=cfg.subnet_dir
    )
    return text, warnings


def _ip_value(value):
    """IP custom field: text value, or the pk of an IP address object."""
    if isinstance(value, int):
        obj = IPAddress.objects.filter(pk=value).first()
        return str(obj.address.ip) if obj else None
    return value


def group_files(dg: DHCPGroup):
    """Generate <Group>_Table and <Group>_StaticTable for one DHCPGroup from its tenants."""
    raw = []
    for t in Tenant.objects.filter(group=dg.group):
        cf = t.custom_field_data or {}
        ip = _ip_value(cf.get(dg.ip_field)) if dg.ip_field else None
        raw.append((t.name, [cf.get(f) for f in dg.mac_fields], ip))
    return build_group_files(dg.group.name, raw, dg.table_template, dg.static_template)
