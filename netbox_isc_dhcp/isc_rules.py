"""Knowledge about ISC dhcpd syntax used by the code checks (no dhcpd binary needed). Pure Python."""
from __future__ import annotations

import ipaddress
import re

# statements allowed inside subnet / pool / host / group / class blocks (first word)
STATEMENTS = {
    "default-lease-time", "max-lease-time", "min-lease-time", "authoritative", "not", "ping-check", "ping-timeout",
    "one-lease-per-client", "update-conflict-detection", "allow", "deny", "ignore", "range", "next-server", "filename",
    "server-name", "server-identifier", "get-lease-hostnames", "use-host-decl-names", "ddns-updates", "ddns-update-style",
    "ddns-domainname", "ddns-rev-domainname", "ddns-hostname", "ddns-ttl", "update-static-leases", "do-forward-updates",
    "update-optimization", "log", "set", "unset", "if", "elsif", "else", "on", "failover", "pool", "subnet", "host",
    "group", "class", "subclass", "match", "spawn", "lease", "fixed-address", "hardware", "include", "option",
    "dynamic-bootp-lease-length", "dynamic-bootp-lease-cutoff", "boot-unknown-clients", "abandon-lease-time",
    "dhcp-cache-threshold", "adaptive-lease-time-threshold", "min-secs", "stash-agent-options", "always-broadcast",
    "always-reply-rfc1048", "ignore-client-uids", "local-address", "client-updates", "execute", "deny-unknown-clients",
    "prefix-length-mode", "echo-client-id", "ping-cltt-secs", "known-clients", "unknown-clients", "lease-id-format",
}
# standard DHCP options (dhcp-options(5)) and the type of their value
OPTIONS = {
    "routers": "iplist", "subnet-mask": "ip", "domain-name-servers": "hostlist", "domain-name": "text",
    "domain-search": "textlist", "broadcast-address": "ip", "ntp-servers": "hostlist", "time-servers": "hostlist",
    "time-offset": "int", "interface-mtu": "int", "tftp-server-name": "text", "bootfile-name": "text",
    "host-name": "text", "netbios-name-servers": "hostlist", "netbios-node-type": "int", "netbios-scope": "text",
    "netbios-dd-server": "hostlist", "static-routes": "any", "vendor-encapsulated-options": "any",
    "vendor-class-identifier": "text", "dhcp-renewal-time": "int", "dhcp-rebinding-time": "int", "dhcp-lease-time": "int",
    "log-servers": "hostlist", "lpr-servers": "hostlist", "smtp-server": "hostlist", "pop-server": "hostlist",
    "www-server": "hostlist", "nis-domain": "text", "nis-servers": "hostlist", "dhcp-server-identifier": "ip",
    "root-path": "text", "dhcp-parameter-request-list": "any", "ip-forwarding": "flag", "default-ip-ttl": "int",
    "domain-name-search": "any", "user-class": "any", "dhcp-client-identifier": "any", "dhcp-max-message-size": "int",
    "dhcp-message": "text", "dhcp-requested-address": "ip", "nwip-domain": "text", "slp-directory-agent": "any",
    "slp-service-scope": "any", "fqdn": "any", "relay-agent-information": "any", "agent": "any", "dhcp-option-overload": "int",
    "all-subnets-local": "flag", "arp-cache-timeout": "int", "ieee802-3-encapsulation": "flag", "router-discovery": "flag",
    "router-solicitation-address": "ip", "swap-server": "ip", "trailer-encapsulation": "flag", "font-servers": "hostlist",
    "x-display-manager": "hostlist", "impress-server": "hostlist", "resource-location-servers": "hostlist",
    "ien116-name-servers": "hostlist", "cookie-servers": "hostlist", "merit-dump": "text", "extensions-path": "text",
    "policy-filter": "any", "max-dgram-reassembly": "int", "path-mtu-aging-timeout": "int", "path-mtu-plateau-table": "any",
    "mask-supplier": "flag", "perform-mask-discovery": "flag", "non-local-source-routing": "flag", "tcp-keepalive-interval": "int",
    "tcp-keepalive-garbage": "flag", "tcp-default-ttl": "int", "boot-size": "int", "streettalk-server": "hostlist",
    "streettalk-directory-assistance-server": "hostlist", "finger-server": "hostlist", "irc-server": "hostlist",
    "nntp-server": "hostlist", "mobile-ip-home-agent": "hostlist", "pxe-system-type": "any", "pxe-interface-id": "any",
    "pxe-client-id": "any", "uap-servers": "text", "geoconf-civic": "any", "pcode": "text", "tcode": "text",
    "netinfo-server-address": "hostlist", "netinfo-server-tag": "text", "default-url": "text", "subnet-selection": "ip",
    "authenticate": "any", "client-last-transaction-time": "int", "associated-ip": "any", "v4-captive-portal": "text",
    "rdnss-selection": "any", "tftp-server-address": "hostlist", "classless-static-routes": "any",
}
# words that may appear in expressions (log, set, if, match...)
EXPR_WORDS = {
    "log", "info", "debug", "error", "fatal", "concat", "binary-to-ascii", "pick-first-value", "leased-address",
    "host-decl-name", "substring", "suffix", "hardware", "packet", "lcase", "ucase", "encode-int", "reverse",
    "extract-int", "config-option", "known", "static", "exists", "client-state", "null", "filename", "server-name",
    "defined", "gethostname", "option", "not", "and", "or", "if", "else", "elsif", "true", "false", "lease-time",
    "ddns-fwd-name", "ddns-rev-name", "ddns-hostname", "ddns-domainname", "client-name", "pick", "execute",
    "set", "unset", "on", "commit", "expiry", "release", "match", "ifdef", "variable-exists", "be", "length",
    "agent", "circuit-id", "remote-id", "relay-agent-information", "dhcp-client-identifier", "host-name",
    "vendor-class-identifier", "user-class", "fqdn", "hostname", "domain-name",
}

_IP = r"\d{1,3}(?:\.\d{1,3}){3}"


def site_definitions(static_text: str) -> dict:
    """What the static part of dhcpd.conf defines: custom options, set variables, classes."""
    text = static_text or ""
    return {
        "options": set(re.findall(r"\boption\s+([A-Za-z0-9_.-]+)\s+code\s+\d+", text)),
        "vars": set(re.findall(r"\bset\s+([A-Za-z0-9_-]+)\s*=", text)),
        "classes": set(re.findall(r'\bclass\s+"([^"]+)"', text)),
    }


def _is_ip(v: str) -> bool:
    try:
        ipaddress.IPv4Address(v)
        return True
    except ValueError:
        return False


def _host_ok(v: str) -> bool:
    return _is_ip(v) or (bool(re.fullmatch(r"[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*", v)) and not re.fullmatch(r"[\d.]+", v))


def check_value(kind: str, value: str) -> str | None:
    """Return an error text when the option value does not fit its type."""
    v = value.strip()
    if kind == "any" or v.startswith(("concat", "pick", "binary", "substring", "suffix", "config-option")):
        return None
    if kind == "ip":
        return None if _is_ip(v) else f"'{v}' is not an IPv4 address"
    if kind == "iplist":
        bad = [x.strip() for x in v.split(",") if not _is_ip(x.strip())]
        return f"'{', '.join(bad)}' is not an IPv4 address" if bad else None
    if kind == "hostlist":
        bad = [x.strip() for x in v.split(",") if not _host_ok(x.strip())]
        return f"'{', '.join(bad)}' is not an IPv4 address or host name" if bad else None
    if kind == "int":
        return None if re.fullmatch(r"-?\d+", v) else f"'{v}' is not a number"
    if kind == "flag":
        return None if v in ("true", "false", "on", "off", "0", "1") else f"'{v}' must be true or false"
    if kind == "text":
        return None if re.fullmatch(r'"[^"]*"', v) else f"'{v}' must be text in quotes"
    if kind == "textlist":
        return None if re.fullmatch(r'"[^"]*"(\s*,\s*"[^"]*")*', v) else f"'{v}' must be texts in quotes separated by commas"
    return None


def expression_words(expr: str) -> list[str]:
    """Bare words of an expression (outside quotes), e.g. the identifiers used in log ( ... )."""
    no_strings = re.sub(r'"[^"]*"', " ", expr)
    return [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", no_strings)]
