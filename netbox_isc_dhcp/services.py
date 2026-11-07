"""Glue between NetBox data and the pure generators."""
from ipam.models import Prefix

from .base_config import render_base_config, split_groups
from .models import BaseConfig, DHCPGroup


def dhcp_prefixes(cfg: BaseConfig) -> list[str]:
    lookup = {f"custom_field_data__{cfg.prefix_field}": cfg.prefix_value}
    return [str(p) for p in Prefix.objects.filter(**lookup).values_list("prefix", flat=True)]


def dhcp_group_names() -> list[str]:
    return [g.group.name for g in DHCPGroup.objects.select_related("group")]


def build_base_config(cfg: BaseConfig) -> tuple[str, list[str]]:
    """Return (dhcpd.conf text, warnings)."""
    names = dhcp_group_names()
    _, rejected = split_groups(names)
    warnings = [f"Group '{n}' skipped: name contains characters not allowed in file names." for n in rejected]
    text = render_base_config(
        cfg.static_text, names, dhcp_prefixes(cfg), table_dir=cfg.table_dir, subnet_dir=cfg.subnet_dir
    )
    return text, warnings
