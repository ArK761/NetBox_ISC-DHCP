"""Level 1: the primary dhcpd.conf = passive part (plain text written by the user)
+ dynamic part (include lists generated here). Pure Python, no NetBox imports."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from importlib import resources

# Group names end up in include paths, so allow only safe characters.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class SubnetInclude:
    network: str
    file: str  # e.g. "10.20.0.0_CFG"


def subnet_includes(prefixes) -> list[SubnetInclude]:
    """One include per IPv4 prefix, numerically sorted, duplicates removed.
    File name is '<network address>_CFG' (same as the current bash script).
    Invalid or IPv6 prefixes are skipped; they must never reach dhcpd.conf."""
    nets: dict[ipaddress.IPv4Network, None] = {}
    for raw in prefixes:
        try:
            net = ipaddress.ip_network(str(raw), strict=True)
        except ValueError:
            continue
        if net.version == 4:
            nets[net] = None
    return [
        SubnetInclude(str(n), f"{n.network_address}_CFG")
        for n in sorted(nets, key=lambda n: (int(n.network_address), n.prefixlen))
    ]


def split_groups(group_names) -> tuple[list[str], list[str]]:
    """Return (valid names in the given order without duplicates, rejected names)."""
    seen, ok, bad = set(), [], []
    for name in group_names:
        if name in seen:
            continue
        seen.add(name)
        (ok if _SAFE_NAME.match(name) else bad).append(name)
    return ok, bad


def default_static_text() -> str:
    return resources.files("netbox_isc_dhcp").joinpath("defaults/dhcpd_static.conf").read_text("utf-8")


_BAD_PATH_CHARS = re.compile(r'[\s"\';{}\\]')


def is_safe_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name or ""))


def is_safe_path(path: str) -> bool:
    """Absolute path without '..', whitespace, quotes or characters that break dhcpd.conf."""
    return bool(path) and path.startswith("/") and ".." not in path.split("/") and not _BAD_PATH_CHARS.search(path)


def render_dynamic_part(table_includes, prefixes, *, subnet_dir="/opt/dhcp/SUBNET") -> str:
    """table_includes: full paths of the table files, in the order they are included."""
    subnet_dir = subnet_dir.rstrip("/")
    lines = [" ### MAC TABLE OR SUBCLASS ##"]
    lines += [f' include "{p}";' for p in table_includes]
    lines.append("### DHCP_POOL ###")
    lines += [f' include "{subnet_dir}/{p.file}";' for p in subnet_includes(prefixes)]
    return "\n".join(lines) + "\n"


def render_base_config(static_text, table_includes, prefixes, **kw) -> str:
    """Passive text is taken verbatim (no template processing), dynamic part follows it."""
    return static_text.rstrip("\n") + "\n\n" + render_dynamic_part(table_includes, prefixes, **kw)
