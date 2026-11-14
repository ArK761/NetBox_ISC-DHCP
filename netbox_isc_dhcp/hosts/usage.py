"""Where a class of a group file is used: allow/deny members of "X" in pool codes, individual subnet codes and the static part of dhcpd.conf."""
import re

_REF = re.compile(r'\b(allow|deny)\s+members\s+of\s+"([^"]+)"', re.I)
_DEF = re.compile(r'^\s*class\s+"([^"]+)"', re.M)


def defined_classes(text) -> list[str]:
    seen = []
    for n in _DEF.findall(text or ""):
        if n not in seen:
            seen.append(n)
    return seen


def _strip_comments(text):
    return "\n".join(line.split("#", 1)[0] for line in (text or "").splitlines())


def references() -> dict:
    """{class name: [{"where": "pool"|"override"|"static", "name", "pk", "subnets", "enabled", "mode"}]}, computed once per call."""
    from ..models import BaseConfig, PoolTemplate, SubnetConfig, SubnetOverride
    from ..source_fields import _field_q
    from ..views import _pool_info, _pool_names

    counts = {}
    cfg = SubnetConfig.objects.first()
    if cfg is not None:
        model, qs, key = _pool_info(cfg)
        if key is not None:
            for value, name in _pool_names(model, qs, key):
                counts[name] = qs.filter(_field_q(model, key["field"], [value])).count()
    out = {}

    def add(text, entry):
        for mode, name in _REF.findall(_strip_comments(text)):
            lst = out.setdefault(name, [])
            e = next((x for x in lst if x["where"] == entry["where"] and x["name"] == entry["name"]), None)
            if e is None:
                lst.append(dict(entry, mode=mode.lower()))
            elif mode.lower() not in e["mode"].split(" / "):
                e["mode"] += " / " + mode.lower()

    for p in PoolTemplate.objects.all():
        add(p.template, {"where": "pool", "name": p.name, "pk": p.pk, "subnets": counts.get(p.name, 0), "enabled": p.enabled})
    for o in SubnetOverride.objects.select_related("pool"):
        add(o.code, {"where": "override", "name": o.prefix_text, "pk": o.pool_id, "subnets": 1, "enabled": o.pool.enabled})
    for b in BaseConfig.objects.all():
        add(b.static_text, {"where": "static", "name": "dhcpd.conf", "pk": b.pk, "subnets": 0, "enabled": True})
    return out


def usage_of(names, refs) -> list[dict]:
    """For every class defined in a file: where it is used and how many subnets."""
    rows = []
    for n in names:
        uses = refs.get(n, [])
        live = [u for u in uses if u["enabled"]]
        rows.append({"name": n, "uses": uses, "used": bool(live),
                     "subnets": sum({(u["where"], u["name"]): u["subnets"] for u in live if u["where"] != "static"}.values()),
                     "in_static": any(u["where"] == "static" for u in uses)})
    return rows


_INC = re.compile(r'^\s*include\s+"([^"]+)"\s*;', re.M)


def included_paths() -> dict:
    """{full path: "plugin" | "static"} of every include in dhcpd.conf (plugin include lines + static part)."""
    from ..models import BaseConfig
    from ..services import table_includes

    out = {p: "plugin" for p in table_includes()[0]}
    for b in BaseConfig.objects.all():
        for p in _INC.findall(_strip_comments(b.static_text)):
            out.setdefault(p, "static")
    return out
