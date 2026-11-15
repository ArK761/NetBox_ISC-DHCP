"""DHCP servers: address (IP or FQDN) -> IPs allowed to download without login."""
import ipaddress
import re
import socket

from django.core.cache import cache

# hostname / FQDN; underscores allowed (common in internal DNS, e.g. dhcp_1)
_FQDN = re.compile(r"^(?=.{1,253}\.?$)([A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.)*[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?\.?$")
CACHE_KEY = "isc_dhcp_server_ips"


def valid_address(a):
    try:
        ipaddress.ip_address(a)
        return True
    except ValueError:
        return bool(_FQDN.match(a or ""))


def resolve(address):
    """(ips, error)."""
    try:
        return [str(ipaddress.ip_address(address))], ""
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(address, None)
        return sorted({i[4][0] for i in infos}), ""
    except OSError as exc:
        return [], str(exc)


def allowed_ips():
    ips = cache.get(CACHE_KEY)
    if ips is None:
        from .models import DHCPServer

        ips = set()
        for s in DHCPServer.objects.filter(enabled=True):
            ips |= set(resolve(s.address)[0])
        cache.set(CACHE_KEY, ips, 300)  # FQDN re-resolved every 5 minutes
    return ips


def invalidate():
    cache.delete(CACHE_KEY)
