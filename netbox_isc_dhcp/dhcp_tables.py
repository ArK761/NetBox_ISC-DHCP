"""TABLE files built from tenants: <Group>_Table (class + optional mismatch class) and
<Group>_StaticTable (host blocks). Pure Python, no NetBox imports."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from importlib import resources
from types import SimpleNamespace

from .renderer import render

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
_HEX12 = re.compile(r"^[0-9A-Fa-f]{12}$")


@dataclass(frozen=True)
class Tenant:
    name: str
    macs: tuple[str, ...]
    ip: str | None = None


@dataclass
class GroupFiles:
    table: str
    static: str
    warnings: list[str]
    dynamic_count: int
    static_count: int


def natural_key(name: str):
    """Natural sort (PC9 < PC10, PCU010 < PCU0011), like the current bash output."""
    return [(1, int(p), "") if p.isdigit() else (0, 0, p) for p in re.split(r"(\d+)", name)]


def normalize_mac(raw) -> str | None:
    if raw is None:
        return None
    s = re.sub(r"[\s:.\-]", "", str(raw))
    return ":".join(s[i : i + 2] for i in range(0, 12, 2)).upper() if _HEX12.match(s) else None


def normalize_ip(raw) -> str | None:
    try:
        return str(ipaddress.IPv4Address(str(raw).strip().split("/")[0]))
    except ValueError:
        return None


def prepare(raw_tenants) -> tuple[list[Tenant], list[Tenant], list[str]]:
    """raw_tenants: iterable of (name, [mac values], ip value). Returns (dynamic, static, warnings).

    - tenant without any MAC: skipped silently (a MAC value that is filled but invalid gives a warning)
    - tenant with IP: static host blocks; without IP: dynamic class
    - duplicate MAC / duplicate static IP / invalid name or IP: skipped with a warning
    """
    warnings: list[str] = []
    dynamic: list[Tenant] = []
    static: list[Tenant] = []
    seen_mac: dict[str, str] = {}
    seen_ip: dict[str, str] = {}
    for name, mac_values, ip_value in sorted(raw_tenants, key=lambda r: natural_key(r[0])):
        macs: list[str] = []
        for v in mac_values:
            if v in (None, ""):
                continue
            m = normalize_mac(v)
            if m is None:
                warnings.append(f"{name}: invalid MAC '{v}' skipped")
            elif m in seen_mac or m in macs:
                warnings.append(f"{name}: MAC {m} already used by {seen_mac.get(m, name)}, skipped")
            else:
                macs.append(m)
        if not macs:
            continue
        if not _SAFE_NAME.match(name):
            warnings.append(f"{name}: tenant name has characters not allowed in DHCP host names, skipped")
            continue
        ip = None
        if ip_value not in (None, ""):
            ip = normalize_ip(ip_value)
            if ip is None:
                warnings.append(f"{name}: invalid IP '{ip_value}', tenant skipped")
                continue
            if ip in seen_ip:
                warnings.append(f"{name}: IP {ip} already used by {seen_ip[ip]}, tenant skipped")
                continue
            seen_ip[ip] = name
        for m in macs:
            seen_mac[m] = name
        (static if ip else dynamic).append(Tenant(name, tuple(macs), ip))
    return dynamic, static, warnings


def default_table_template() -> str:
    return resources.files("netbox_isc_dhcp").joinpath("defaults/table_workstation.j2").read_text("utf-8")


def default_static_template() -> str:
    return resources.files("netbox_isc_dhcp").joinpath("defaults/static_default.j2").read_text("utf-8")


def build_group_files(class_name, raw_tenants, table_template=None, static_template=None) -> GroupFiles:
    """Render the two files of a group from its two (user editable) Jinja templates.

    Context: class_name; tenants (dynamic: .name .macs); pairs (one per dynamic MAC: .name .mac);
    static_tenants (.name .macs .ip); hosts (one per static MAC: .host .name .mac .ip, host has the
    _1/_2/_3 suffix when the tenant has several MACs)."""
    dynamic, static, warnings = prepare(raw_tenants)
    pairs = [SimpleNamespace(name=t.name, mac=m) for t in dynamic for m in t.macs]
    hosts = [
        SimpleNamespace(host=t.name if len(t.macs) == 1 else f"{t.name}_{i}", name=t.name, mac=m, ip=t.ip)
        for t in static
        for i, m in enumerate(t.macs, 1)
    ]
    ctx = {"class_name": class_name, "tenants": dynamic, "pairs": pairs, "static_tenants": static, "hosts": hosts}
    return GroupFiles(
        table=render(table_template or default_table_template(), ctx),
        static=render(static_template or default_static_template(), ctx),
        warnings=warnings,
        dynamic_count=len(dynamic),
        static_count=len(static),
    )
