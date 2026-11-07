"""Level 1: the primary dhcpd.conf. Static text (editable template) plus two generated lists."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from importlib import resources

from .renderer import render

# Group names end up in include paths, so allow only safe characters.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SubnetInclude:
    network: str
    file: str  # e.g. "10.20.0.0_CFG"


def subnet_includes(prefixes: list[str]) -> list[SubnetInclude]:
    """One include per IPv4 prefix, numerically sorted, duplicates removed.

    File name is '<network address>_CFG' (same naming as the current bash script).
    Invalid or IPv6 prefixes are skipped; they must never reach dhcpd.conf.
    """
    nets: dict[ipaddress.IPv4Network, None] = {}
    for raw in prefixes:
        try:
            net = ipaddress.ip_network(raw, strict=True)
        except ValueError:
            continue
        if net.version == 4:
            nets[net] = None
    return [
        SubnetInclude(str(n), f"{n.network_address}_CFG")
        for n in sorted(nets, key=lambda n: (int(n.network_address), n.prefixlen))
    ]


def clean_groups(group_names: list[str]) -> list[str]:
    """Keep the given order (it is chosen by the caller), drop unsafe names and duplicates."""
    seen, out = set(), []
    for name in group_names:
        if name in seen or not _SAFE_NAME.match(name):
            continue
        seen.add(name)
        out.append(name)
    return out


def default_template() -> str:
    return resources.files("netbox_isc_dhcp").joinpath("templates/dhcpd.conf.j2").read_text("utf-8")


def render_base_config(
    group_names: list[str],
    prefixes: list[str],
    *,
    template_text: str | None = None,
    table_dir: str = "/opt/dhcp/TABLE",
    subnet_dir: str = "/opt/dhcp/SUBNET",
) -> str:
    context = {
        "groups": clean_groups(group_names),
        "prefixes": subnet_includes(prefixes),
        "table_dir": table_dir.rstrip("/"),
        "subnet_dir": subnet_dir.rstrip("/"),
    }
    return render(template_text if template_text is not None else default_template(), context)
