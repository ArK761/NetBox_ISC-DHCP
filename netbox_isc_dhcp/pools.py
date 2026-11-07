"""Pool layout calculation for one IPv4 prefix. Pure Python, no NetBox imports.

Layout of the `WorkStation` profile (derived from the original /24 template):

    .0          network
    .1          gateway (default, can be overridden)
    .2 - .10    reserved for static devices
    .11 - ...   dynamic pool (known clients, class "WorkStation")
    -16 - -9    mismatch pool (8 addresses, relative to the broadcast address)
    -8  - -2    unknown pool (7 addresses)
    -1          broadcast

For 10.20.0.0/24 this gives dynamic .11-.239, mismatch .240-.247, unknown .248-.254,
identical to the old bash template. Smaller prefixes are scaled automatically and
rejected with PoolLayoutError when the ranges do not fit.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass

RESERVED_STATIC = 10  # offsets 1..10 are gateway + static devices
MISMATCH_SIZE = 8
UNKNOWN_SIZE = 7


class PoolLayoutError(ValueError):
    """The requested pool layout is not valid for the given prefix."""


@dataclass(frozen=True)
class IPRange:
    first: ipaddress.IPv4Address
    last: ipaddress.IPv4Address

    @property
    def size(self) -> int:
        return int(self.last) - int(self.first) + 1

    def contains(self, ip: ipaddress.IPv4Address) -> bool:
        return self.first <= ip <= self.last

    def overlaps(self, other: "IPRange") -> bool:
        return self.first <= other.last and other.first <= self.last


@dataclass(frozen=True)
class PoolPlan:
    network: ipaddress.IPv4Network
    gateway: ipaddress.IPv4Address
    broadcast: ipaddress.IPv4Address
    dynamic: IPRange
    mismatch: IPRange
    unknown: IPRange

    @property
    def netmask(self) -> str:
        return str(self.network.netmask)

    @property
    def three_octet(self) -> str:
        """First three octets, e.g. '10.20.0' (kept for template compatibility)."""
        return ".".join(str(self.network.network_address).split(".")[:3])


def plan_workstation_pools(
    prefix: str,
    *,
    gateway: str | None = None,
    min_prefix_length: int = 26,
    min_dynamic_addresses: int = 10,
) -> PoolPlan:
    try:
        net = ipaddress.ip_network(prefix, strict=True)
    except ValueError as exc:
        raise PoolLayoutError(f"Invalid prefix {prefix!r}: {exc}") from exc
    if net.version != 4:
        raise PoolLayoutError("Only IPv4 prefixes are supported")
    if net.prefixlen > min_prefix_length:
        raise PoolLayoutError(
            f"{net} is too small for the WorkStation profile "
            f"(minimum is /{min_prefix_length})"
        )
    if net.prefixlen < 16:
        raise PoolLayoutError(f"{net} is too large for a single DHCP subnet (maximum is /16)")

    base = int(net.network_address)
    broadcast = ipaddress.IPv4Address(int(net.broadcast_address))
    gw = ipaddress.IPv4Address(gateway) if gateway else ipaddress.IPv4Address(base + 1)
    if gw not in net or gw in (net.network_address, broadcast):
        raise PoolLayoutError(f"Gateway {gw} is not a usable address in {net}")

    unknown = IPRange(
        ipaddress.IPv4Address(int(broadcast) - UNKNOWN_SIZE),
        ipaddress.IPv4Address(int(broadcast) - 1),
    )
    mismatch_last = int(unknown.first) - 1
    mismatch = IPRange(
        ipaddress.IPv4Address(mismatch_last - MISMATCH_SIZE + 1),
        ipaddress.IPv4Address(mismatch_last),
    )
    dyn_first = ipaddress.IPv4Address(base + RESERVED_STATIC + 1)
    dyn_last = ipaddress.IPv4Address(int(mismatch.first) - 1)
    if int(dyn_last) - int(dyn_first) + 1 < min_dynamic_addresses:
        raise PoolLayoutError(
            f"{net}: dynamic pool would have fewer than {min_dynamic_addresses} addresses"
        )
    dynamic = IPRange(dyn_first, dyn_last)

    plan = PoolPlan(net, gw, broadcast, dynamic, mismatch, unknown)
    _validate(plan)
    return plan


def _validate(plan: PoolPlan) -> None:
    ranges = {"dynamic": plan.dynamic, "mismatch": plan.mismatch, "unknown": plan.unknown}
    names = list(ranges)
    for i, a in enumerate(names):
        r = ranges[a]
        if not (plan.network.network_address < r.first and r.last < plan.broadcast):
            raise PoolLayoutError(f"{a} pool {r.first}-{r.last} is outside {plan.network}")
        if r.first > r.last:
            raise PoolLayoutError(f"{a} pool is empty")
        if r.contains(plan.gateway):
            raise PoolLayoutError(f"{a} pool contains the gateway {plan.gateway}")
        for b in names[i + 1 :]:
            if r.overlaps(ranges[b]):
                raise PoolLayoutError(f"{a} and {b} pools overlap")


def check_static_conflicts(plan: PoolPlan, static_ips: list[str]) -> list[str]:
    """Return static IPs (e.g. from NetBox IPAddress objects) that fall inside dynamic pools."""
    conflicts = []
    for raw in static_ips:
        ip = ipaddress.IPv4Address(raw.split("/")[0])
        if any(r.contains(ip) for r in (plan.dynamic, plan.mismatch, plan.unknown)):
            conflicts.append(str(ip))
    return conflicts
