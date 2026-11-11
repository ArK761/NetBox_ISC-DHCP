"""Own variables: named pieces of ISC config built from a catalog of ISC options. Pure Python.

In pool code a line `USE <name>` is replaced by the variable's lines (indentation kept)."""
from __future__ import annotations

import ipaddress
import re

# key: (label, group, kind, pattern). kind decides the value input and how the line is built.
CATALOG = {
    "lease": ("default-lease-time + max-lease-time", "lease", "lease", ""),
    "min-lease-time": ("min-lease-time", "lease", "number", "min-lease-time {v};"),
    "domain-name-servers": ("option domain-name-servers", "dns", "dns", "option domain-name-servers {v};"),
    "domain-name": ("option domain-name", "dns", "quoted", 'option domain-name {v};'),
    "domain-search": ("option domain-search", "dns", "quotedlist", "option domain-search {v};"),
    "range": ("range (start end)", "net", "range", "range {v};"),
    "broadcast-address": ("option broadcast-address", "net", "ip", "option broadcast-address {v};"),
    "interface-mtu": ("option interface-mtu", "net", "number", "option interface-mtu {v};"),
    "time-offset": ("option time-offset", "net", "number", "option time-offset {v};"),
    "ntp-servers": ("option ntp-servers", "net", "iplist", "option ntp-servers {v};"),
    "unknown-clients": ("allow / deny unknown-clients", "access", "allowdeny", "{v} unknown-clients;"),
    "duplicates": ("allow / deny duplicates", "access", "allowdeny", "{v} duplicates;"),
    "one-lease-per-client": ("one-lease-per-client", "access", "truefalse", "one-lease-per-client {v};"),
    "ping-check": ("ping-check", "access", "truefalse", "ping-check {v};"),
    "update-conflict-detection": ("update-conflict-detection", "access", "truefalse", "update-conflict-detection {v};"),
    "next-server": ("next-server", "pxe", "ip", "next-server {v};"),
    "filename": ("filename", "pxe", "quoted", "filename {v};"),
    "tftp-server-name": ("option tftp-server-name", "pxe", "quoted", "option tftp-server-name {v};"),
    "ddns-updates": ("ddns-updates", "ddns", "onoff", "ddns-updates {v};"),
    "ddns-domainname": ("ddns-domainname", "ddns", "quoted", "ddns-domainname {v};"),
    "raw": ("raw", "own", "raw", "{v}"),
}
NAME_RE = re.compile(r"^[A-Za-z0-9_./-]{1,60}$")
USE_RE = re.compile(r"^(?P<indent>[ \t]*)USE[ \t]+(?P<name>\S+)[ \t]*$", re.M)


class VariableError(ValueError):
    pass


def kind_of(option: str) -> str:
    return CATALOG.get(option, ("", "", "raw", ""))[2]


def build_lines(option: str, value: str, dns_ips=(), lease_factor: float = 1.3) -> str:
    """The ISC line(s) a variable stands for. Raises VariableError for an invalid value."""
    if option not in CATALOG:
        raise VariableError(f"unknown ISC option {option!r}")
    _, _, kind, pattern = CATALOG[option]
    value = (value or "").strip()
    if kind == "lease":
        if not value.isdigit() or int(value) <= 0:
            raise VariableError("lease must be a positive number of seconds")
        return f"default-lease-time {int(value)};\nmax-lease-time {round(int(value) * lease_factor)};"
    if kind == "dns":
        if not dns_ips:
            raise VariableError("pick at least one DNS server")
        v = ", ".join(dns_ips)
    elif kind == "number":
        if not re.fullmatch(r"-?\d+", value):
            raise VariableError("value must be a whole number")
        v = value
    elif kind == "ip":
        try:
            v = str(ipaddress.IPv4Address(value))
        except ValueError as exc:
            raise VariableError("value must be an IPv4 address") from exc
    elif kind == "range":
        parts = [x for x in re.split(r"[\s,;-]+", value) if x]
        try:
            a, b = (ipaddress.IPv4Address(x) for x in parts) if len(parts) == 2 else (None, None)
        except ValueError:
            a = b = None
        if a is None:
            raise VariableError("range needs two IPv4 addresses: start end")
        if a > b:
            raise VariableError("range: start is after end")
        v = f"{a} {b}"
    elif kind == "iplist":
        try:
            v = ", ".join(str(ipaddress.IPv4Address(x.strip())) for x in value.split(",") if x.strip())
        except ValueError as exc:
            raise VariableError("value must be IPv4 addresses separated by commas") from exc
        if not v:
            raise VariableError("enter at least one address")
    elif kind == "quoted":
        if not value or '"' in value:
            raise VariableError("enter a text without quotes (they are added automatically)")
        v = f'"{value}"'
    elif kind == "quotedlist":
        items = [x.strip() for x in value.split(",") if x.strip()]
        if not items or any('"' in x for x in items):
            raise VariableError("enter texts separated by commas, without quotes")
        v = ", ".join(f'"{x}"' for x in items)
    elif kind == "allowdeny":
        if value not in ("allow", "deny"):
            raise VariableError("choose allow or deny")
        v = value
    elif kind == "truefalse":
        if value not in ("true", "false"):
            raise VariableError("choose true or false")
        v = value
    elif kind == "onoff":
        if value not in ("on", "off"):
            raise VariableError("choose on or off")
        v = value
    else:  # raw
        if not value:
            raise VariableError("enter the text")
        v = value
    return pattern.format(v=v)


def normalize(text: str) -> str:
    """Browsers send textarea content with CRLF line ends; dhcpd and USE matching want LF."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def used_names(text: str) -> set[str]:
    return {m.group("name") for m in USE_RE.finditer(normalize(text))}


def rename_use(text: str, old: str, new: str) -> str:
    """Rewrite every `USE <old>` line to `USE <new>` (indentation kept)."""
    pattern = re.compile(r"^(?P<indent>[ \t]*)USE[ \t]+" + re.escape(old) + r"[ \t]*$", re.M)
    return pattern.sub(lambda m: m.group("indent") + "USE " + new, normalize(text))


VAR_COMMENT = "## VARIABLE ADDED VIA OWN VARIABLES"


def expand_use(template: str, snippets: dict[str, str], invalid=()) -> tuple[str, list[str]]:
    """Replace every `USE <name>` line by the snippet lines (same indentation), each marked with a trailing
    comment `## added via own variable <name> ##`. Unknown names / variables without a valid value are errors."""
    errors: list[str] = []

    def repl(m):
        name, indent = m.group("name"), m.group("indent")
        if name not in snippets:
            errors.append(f"USE {name}: variable has no valid value" if name in invalid else f"USE {name}: unknown variable")
            return m.group(0)
        return "\n".join(f"{indent}{line} ## added via own variable {name} ##" for line in snippets[name].splitlines())

    return USE_RE.sub(repl, normalize(template)), errors
