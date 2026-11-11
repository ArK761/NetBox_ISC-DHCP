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
    return errors


# statements that may legally appear several times in one block
_REPEATABLE = {"range", "allow", "deny", "log", "if", "elsif", "else", "on", "pool", "host", "class", "subclass",
               "match", "spawn", "set", "unset", "execute", "ignore", "next-server", "include"}


def structure_errors(text: str, prefix: str, site: dict | None = None, known_classes=(), lenient: bool = False) -> list[str]:
    """Basic ISC syntax checks of a subnet file (no dhcpd needed):
    everything inside one `subnet <network> netmask <mask> { }` block, `;` at the end of statements,
    closed quotes and parentheses, balanced braces, no option twice in the same block."""
    from .isc_rules import EXPR_WORDS, OPTIONS, STATEMENTS, check_value, expression_words

    net = _net(prefix)
    site = site or {"options": set(), "vars": set(), "classes": set()}
    classes = set(known_classes) | set(site.get("classes", ()))
    errors: list[str] = []
    depth, seen_stack, subnets = 0, [set()], 0
    lease = [{}]  # default/max lease per block
    stmt, stmt_line = "", 0
    for no, raw in enumerate(text.splitlines(), 1):
        # drop comments (a # outside quotes)
        line, q = "", False
        for ch in raw:
            if ch == '"':
                q = not q
            if ch == "#" and not q:
                break
            line += ch
        if not line.strip():
            continue
        if not stmt:
            stmt_line = no
        stmt += (" " if stmt else "") + line.strip()
        # a statement ends with ; { or } outside quotes and parentheses
        quotes = stmt.count('"') % 2
        parens = stmt.count("(") - stmt.count(")")
        if quotes or parens > 0:
            if no == len(text.splitlines()):
                errors.append(f"line {stmt_line}: unclosed {'quote' if quotes else 'parenthesis'}")
            continue
        if parens < 0:
            errors.append(f"line {stmt_line}: too many closing parentheses")
        while stmt:
            stmt = stmt.strip()
            if stmt.startswith("}"):
                depth -= 1
                if depth < 0:
                    errors.append(f"line {no}: closing brace without an open block")
                    depth = 0
                elif len(seen_stack) > 1:
                    seen_stack.pop()
                    lease.pop()
                stmt = stmt[1:]
                continue
            cut = min([i for i in (stmt.find(";"), stmt.find("{"), stmt.find("}")) if i >= 0] or [-1])
            if cut < 0:
                break
            body, end = stmt[:cut].strip(), stmt[cut]
            stmt = stmt[cut + 1:] if end != "}" else stmt[cut:]
            if not body:
                continue
            words = body.split()
            if depth == 0:
                if words[0] != "subnet":
                    errors.append(f"line {stmt_line}: '{body[:60]}' is outside the subnet block")
                elif end == "{":
                    subnets += 1
                    if len(words) < 4 or words[1] != str(net.network_address) or words[3] != str(net.netmask):
                        errors.append(f"line {stmt_line}: subnet must be '{net.network_address} netmask {net.netmask}'")
            errors += _statement_errors(stmt_line, body, words, depth, net, site, classes,
                                        STATEMENTS, OPTIONS, EXPR_WORDS, check_value, expression_words, lease, lenient)
            if end == "{":
                depth += 1
                seen_stack.append(set())
                lease.append({})
                continue
            key = " ".join(words[:2]) if words[0] in ("option", "allow", "deny") and len(words) > 1 else words[0]
            if words[0] not in _REPEATABLE:
                if key in seen_stack[-1]:
                    errors.append(f"line {stmt_line}: '{key}' is set twice in the same block")
                seen_stack[-1].add(key)
        if stmt.strip() and not stmt.strip().startswith("}"):
            # text left without ; { } at the end of the line
            if not re.search(r"[;{}]\s*$", line):
                errors.append(f"line {stmt_line}: missing ';' at the end of '{stmt.strip()[:60]}'")
                stmt = ""
    if depth > 0:
        errors.append("missing closing brace '}'")
    if subnets == 0:
        errors.append("no 'subnet ... netmask ... {' block")
    elif subnets > 1:
        errors.append("more than one subnet block")
    return errors


def _statement_errors(no, body, words, depth, net, site, classes, STATEMENTS, OPTIONS, EXPR_WORDS, check_value, expression_words, lease,
                      lenient=False):
    """Keyword, value and reference checks of one statement."""
    errs, w0 = [], words[0]
    short = body if len(body) <= 70 else body[:67] + "..."
    if w0 not in STATEMENTS:
        errs.append(f"line {no}: unknown statement '{w0}' in '{short}'")
        return errs
    if w0 == "option" and len(words) >= 2:
        name, value = words[1], body.split(None, 2)[2] if len(words) > 2 else ""
        kind = OPTIONS.get(name)
        if kind is None and lenient:
            pass
        elif kind is None and name not in site.get("options", ()):
            errs.append(f"line {no}: unknown option '{name}' (not a standard ISC option and not defined in the static part)")
        elif kind and not value.strip():
            errs.append(f"line {no}: option '{name}' has no value")
        elif kind:
            bad = check_value(kind, value)
            if bad:
                errs.append(f"line {no}: option {name}: {bad}")
            elif name == "subnet-mask" and depth == 1 and value.strip() != str(net.netmask):
                errs.append(f"line {no}: option subnet-mask {value.strip()} differs from the subnet mask {net.netmask}")
            elif name == "routers" and depth == 1:
                for r in [x.strip() for x in value.split(",")]:
                    a = ipaddress.IPv4Address(r)
                    if a not in net or a in (net.network_address, net.broadcast_address):
                        errs.append(f"line {no}: option routers {r} is not a usable address of {net}")
    elif w0 in ("default-lease-time", "max-lease-time", "min-lease-time"):
        if len(words) != 2 or not words[1].isdigit():
            errs.append(f"line {no}: {w0} needs a number of seconds")
        else:
            lease[-1][w0] = int(words[1])
            d, m = lease[-1].get("default-lease-time"), lease[-1].get("max-lease-time")
            if d is not None and m is not None and d > m:
                errs.append(f"line {no}: default-lease-time {d} is greater than max-lease-time {m}")
    elif w0 in ("allow", "deny", "ignore") and len(words) >= 3 and words[1] == "members" and words[2] == "of":
        m = re.search(r'"([^"]+)"', body)
        if m and classes and not lenient and m.group(1) not in classes:
            errs.append(f"line {no}: class \"{m.group(1)}\" is not defined (tenant tables or static part)")
    elif w0 in ("next-server",) and len(words) >= 2:
        bad = check_value("hostlist", words[1])
        if bad:
            errs.append(f"line {no}: next-server: {bad}")
    elif w0 in ("filename", "server-name") and len(words) >= 2:
        bad = check_value("text", body.split(None, 1)[1])
        if bad:
            errs.append(f"line {no}: {w0}: {bad}")
    if w0 in ("log", "set", "if", "elsif", "match") and not lenient:
        known = EXPR_WORDS | set(OPTIONS) | set(site.get("vars", ())) | set(site.get("options", ()))
        unknown = sorted({x for x in expression_words(body) if x not in known})
        if unknown:
            errs.append(f"line {no}: unknown word(s) {', '.join(unknown)} in '{short}' (a variable must be defined with 'set' in the static part)")
    return errs


def render_subnet(template: str, prefix: str, dns=(), extra=None, gateway_mode: str = "first", snippets=None,
                  site=None, known_classes=(), lenient: bool = False) -> tuple[str, list[str]]:
    """Return (text, errors). Errors mean the file must NOT be used. `USE <name>` lines are expanded first."""
    from .variables import expand_use

    template, use_errors = expand_use(template, snippets or {})
    if use_errors:
        return "", use_errors
    try:
        text = render(template, context(prefix, dns, extra, gateway_mode))
    except (RenderError, SubnetError) as exc:
        return "", [str(exc)]
    return text, structure_errors(text, prefix, site, known_classes, lenient) + validate(text, prefix)
