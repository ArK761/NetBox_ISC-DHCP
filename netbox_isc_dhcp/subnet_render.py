"""Render one subnet file (<network>_CFG) from a pool template and check the result. Pure Python."""
from __future__ import annotations

import ipaddress
import re

from .renderer import RenderError, render

DEFAULT_POOL_TEMPLATE = """subnet {{ network }} netmask {{ netmask }} {
    option routers {{ gateway }};
    option subnet-mask {{ netmask }};
{% if dns %}
    option domain-name-servers {{ dns|join(", ") }};
{% endif %}
    pool {
        range {{ ip(10) }} {{ ip(-2) }};
    }
}
"""


class SubnetError(ValueError):
    pass


def default_pool_template() -> str:
    return DEFAULT_POOL_TEMPLATE


def _net(prefix: str) -> ipaddress.IPv4Network:
    try:
        net = ipaddress.ip_network(str(prefix), strict=True)
    except ValueError as exc:
        raise SubnetError(f"Invalid prefix {prefix!r}: {exc}") from exc
    if net.version != 4 or net.prefixlen > 30:
        raise SubnetError(f"{net}: only IPv4 prefixes with at least 2 usable addresses")
    return net


def context(prefix: str, dns=(), extra=None, gateway_mode: str = "first") -> dict:
    """Variables for the pool template. ip(n): n>0 from the network address, n<0 from the broadcast (-1 = last usable)."""
    net = _net(prefix)
    base, bc = int(net.network_address), int(net.broadcast_address)

    def ip(n: int) -> str:
        n = int(n)
        addr = base + n if n > 0 else bc + n
        if n == 0 or not base < addr < bc:
            raise SubnetError(f"ip({n}) is outside the usable addresses of {net}")
        return str(ipaddress.IPv4Address(addr))

    ctx = {
        "prefix": str(net), "network": str(net.network_address), "netmask": str(net.netmask), "prefixlen": net.prefixlen,
        "broadcast": str(net.broadcast_address), "first_usable": ip(1), "last_usable": ip(-1),
        "size": net.num_addresses, "three_octet": ".".join(str(net.network_address).split(".")[:3]),
        "ip": ip, "dns": list(dns),
        "gateway": ip(-1) if gateway_mode == "last" else ip(1),  # global rule: first (or last) usable address
    }
    ctx.update(extra or {})
    return ctx


_RANGE = re.compile(r"\brange\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s*;", re.M)


def validate(text: str, prefix: str) -> list[str]:
    """Errors that would break dhcpd: ranges outside the prefix, reversed or overlapping, unbalanced braces."""
    net = _net(prefix)
    errors, ranges = [], []
    for a, b in _RANGE.findall(text):
        try:
            x, y = ipaddress.IPv4Address(a), ipaddress.IPv4Address(b)
        except ValueError:
            errors.append(f"range {a} {b}: invalid address")
            continue
        if not (x in net and y in net) or x in (net.network_address, net.broadcast_address) or y in (net.network_address, net.broadcast_address):
            errors.append(f"range {a} {b} is not inside the usable addresses of {net}")
        elif x > y:
            errors.append(f"range {a} {b}: start is after end")
        else:
            for c, d in ranges:
                if x <= d and c <= y:
                    errors.append(f"range {a} {b} overlaps range {c} {d}")
            ranges.append((x, y))
    gw = re.search(r"option\s+routers\s+(\d+\.\d+\.\d+\.\d+)", text)
    if gw:
        for c, d in ranges:
            if c <= ipaddress.IPv4Address(gw.group(1)) <= d:
                errors.append(f"gateway {gw.group(1)} is inside range {c} {d}")
    if text.count("{") != text.count("}"):
        errors.append("unbalanced { } braces")
    return errors


def render_subnet(template: str, prefix: str, dns=(), extra=None, gateway_mode: str = "first", snippets=None) -> tuple[str, list[str]]:
    """Return (text, errors). Errors mean the file must NOT be used. `USE <name>` lines are expanded first."""
    from .variables import expand_use

    template, use_errors = expand_use(template, snippets or {})
    if use_errors:
        return "", use_errors
    try:
        text = render(template, context(prefix, dns, extra, gateway_mode))
    except (RenderError, SubnetError) as exc:
        return "", [str(exc)]
    return text, validate(text, prefix)
