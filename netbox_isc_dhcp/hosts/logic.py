"""Hosts: read groups (DHCP classes) and MAC/IP objects from any NetBox object type."""
from django.db import models

from ..dhcp_tables import _SAFE_NAME, Tenant, natural_key, normalize_ip, normalize_mac
from ..source_fields import _custom_field, build_q, distinct_values, field_options, get_model, is_active, label_for

MAX_MAC_FIELDS = 3


def _scalar(obj):
    """Text value of a related object: IP address object -> IP, MAC address object -> MAC, else its name."""
    if obj is None:
        return None
    for attr in ("address", "mac_address"):
        a = getattr(obj, attr, None)
        if a is not None:
            return str(getattr(a, "ip", a))
    return str(obj)


def read_value(obj, key):
    if not key:
        return None
    if key.startswith("cf_"):
        v = (obj.custom_field_data or {}).get(key[3:])
        cf = _custom_field(type(obj), key)
        if cf is not None and cf.type == "object" and v not in (None, ""):
            m = cf.related_object_type.model_class() if cf.related_object_type else None
            return _scalar(m.objects.filter(pk=v).first()) if m else None
        return v
    v = getattr(obj, key, None)
    return _scalar(v) if isinstance(v, models.Model) else v


def name_of(obj, key) -> str:
    """Name taken from the chosen field (empty field -> the object's own name)."""
    v = read_value(obj, key) if key else None
    return str(v).strip() if v not in (None, "") else str(obj)


MAX_VALUES = 300


def condition_rows(model, conds, open_row=None) -> list[dict]:
    """Conditions for the page: field label, mode, summary of the ticked values; the list of every value
    of the field is built only for the row that is open."""
    rows = []
    for i, c in enumerate(conds):
        ticked = [str(v) for v in c.get("values") or []]
        vals = distinct_values(model, c["field"]) if model is not None else []
        names = dict(vals)
        shown = [names.get(v, v) for v in ticked[:4]]
        rows.append({"index": i, "field": c["field"], "label": label_for(model, c["field"]), "mode": c.get("mode", "include"),
                     "summary": ", ".join(shown) + (f" … (+{len(ticked) - 4})" if len(ticked) > 4 else ""), "ticked": len(ticked),
                     "open": i == open_row,
                     "values": [(v, l, v in ticked) for v, l in vals[:MAX_VALUES]] if i == open_row else [],
                     "more": max(0, len(vals) - MAX_VALUES)})
    return rows


def groups_overview(cfg, open_row=None) -> dict:
    """Groups of the table source (all, or filtered by the conditions), each with its HostGroup settings and host counts."""
    from .models import HostGroup

    gm = get_model(cfg.group_model)
    out = {"group_model": gm, "groups": [], "conditions": []}
    if gm is None:
        return out
    conds = []  # owner: no table-source conditions, the per-group switch is enough
    out["conditions"] = condition_rows(gm, conds, open_row)
    active = [c for c in conds if is_active(c)]
    qs = gm.objects.filter(build_q(gm, active)) if active else gm.objects.all()
    gkeys = {o["key"] for o in field_options(gm)}
    gname = cfg.group_name_field if cfg.group_name_field in gkeys else ""
    existing = {hg.group_pk: hg for hg in HostGroup.objects.filter(group_model=cfg.group_model)}
    rows = []
    for g in qs:
        name = name_of(g, gname)
        hg = existing.get(g.pk)
        if hg is None:
            hg = HostGroup.objects.create(group_model=cfg.group_model, group_pk=g.pk, name=name[:200])
        elif hg.name != name[:200]:
            hg.name = name[:200]
            hg.save(update_fields=["name"])
        row = {"obj": g, "hg": hg, "name": name, "valid": bool(_SAFE_NAME.match(name))}
        row.update(build_group(hg))
        if not row["objects"]:  # nothing from the sources yet: what NetBox links to the group
            row["objects"], row["objects_of"] = related_count(g)
        rows.append(row)
    out["groups"] = sorted(rows, key=lambda r: natural_key(r["name"]))
    out["total"] = gm.objects.count()
    return out


def related_count(group_obj):
    """Objects NetBox itself links to the group (e.g. tenants of a tenant group): (count, object label)."""
    best = (0, "")
    for rel in type(group_obj)._meta.related_objects:
        if not rel.one_to_many or rel.related_model is type(group_obj):
            continue
        try:
            n = rel.related_model.objects.filter(**{rel.field.name: group_obj}).count()
        except Exception:
            continue
        if n > best[0] or not best[1]:
            best = (n, str(rel.related_model._meta.verbose_name_plural))
    return best


def source_info(src, open_row=None) -> dict:
    """One source for the page: object, conditions, what is still missing."""
    mm = get_model(src.model)
    keys = {o["key"] for o in field_options(mm)}
    conds = [c for c in src.conditions or [] if c.get("field")]
    need = []
    if mm is None:
        need.append("model")
    else:
        if not any(is_active(c) for c in conds):
            need.append("cond")
        if not [k for k in src.mac_fields or [] if k in keys]:
            need.append("mac")
        if src.kind == "static" and src.ip_field not in keys:
            need.append("ip")
    return {"src": src, "model": mm, "need": need, "conditions": condition_rows(mm, conds, open_row) if mm else []}


def prepare_hosts(raw, static):
    """raw: (name, [mac values], ip). Duplicate MAC / IP are only warnings (dhcpd accepts them);
    left out: invalid MAC / IP / name and, in the static file, a second host block with the same name."""
    hosts, warnings, mac_owners, ip_owners, blocks = [], [], {}, {}, set()
    for name, mac_values, ip_value in sorted(raw, key=lambda r: natural_key(r[0])):
        macs = []
        for v in mac_values:
            if v in (None, ""):
                continue
            m = normalize_mac(v)
            if m is None:
                warnings.append(f"{name}: invalid MAC '{v}' skipped")
            elif m not in macs:
                macs.append(m)
        if not macs:
            continue
        if not _SAFE_NAME.match(name):
            warnings.append(f"{name}: tenant name has characters not allowed in DHCP host names, skipped")
            continue
        ip = None
        if static:
            ip = normalize_ip(ip_value)
            if ip is None:
                warnings.append(f"{name}: invalid IP '{ip_value}', tenant skipped")
                continue
            names = [name] if len(macs) == 1 else [f"{name}_{i}" for i in range(1, len(macs) + 1)]
            if blocks & set(names):
                warnings.append(f"{name}: host name already used in this file, skipped")
                continue
            blocks.update(names)
            ip_owners.setdefault(ip, []).append(name)
        for m in macs:
            mac_owners.setdefault(m, []).append(name)
        hosts.append(Tenant(name, tuple(macs), ip))
    for m, owners in mac_owners.items():
        if len(owners) > 1:
            warnings.append(f"duplicate MAC {m}: {', '.join(owners)}")
    for i, owners in ip_owners.items():
        if len(owners) > 1:
            warnings.append(f"duplicate IP {i}: {', '.join(owners)}")
    return hosts, warnings


def build_group(hg) -> dict:
    """Both files of a group from all their sources: hosts, warnings, counts."""
    out = {"objects": 0, "warnings": [], "has_sources": False}
    macs_of = {}
    for kind in ("dynamic", "static"):
        raw, objects, no_ip, with_ip, configured = [], 0, 0, 0, 0
        for src in hg.sources.filter(kind=kind):
            out["has_sources"] = True
            info = source_info(src)
            if info["need"]:
                continue
            configured += 1
            mm, keys = info["model"], {o["key"] for o in field_options(info["model"])}
            macs = [k for k in src.mac_fields if k in keys]
            hname = src.host_name_field if src.host_name_field in keys else ""
            active = [c for c in src.conditions if c.get("field") and is_active(c)]
            ipf = src.ip_field if src.ip_field in keys else ""
            for o in mm.objects.filter(build_q(mm, active)):
                objects += 1
                ip = read_value(o, ipf) if ipf else None
                if kind == "static" and ip in (None, ""):
                    no_ip += 1
                    continue
                if kind == "dynamic" and ip not in (None, ""):  # has a static IP: belongs to the static file
                    with_ip += 1
                    continue
                ip = ip if kind == "static" else None
                raw.append((name_of(o, hname), [read_value(o, k) for k in macs], ip))
        hosts, warn = prepare_hosts(raw, kind == "static")
        macs_of[kind] = {m: t.name for t in hosts for m in t.macs}
        out[kind] = {"hosts": hosts, "macs": sum(len(t.macs) for t in hosts), "objects": objects, "no_ip": no_ip, "with_ip": with_ip,
                     "skipped": objects - no_ip - with_ip - len(hosts), "configured": configured}
        out["objects"] += objects
        out["warnings"] += [f"{hg.file_name(kind)}: {w}" for w in warn]
    out["skipped"] = out["dynamic"]["skipped"] + out["static"]["skipped"]
    out["source_labels"] = sorted({str(get_model(x.model)._meta.verbose_name).capitalize() for x in hg.sources.all() if get_model(x.model)})
    out["source_count"] = hg.sources.count()
    for m in sorted(set(macs_of["dynamic"]) & set(macs_of["static"])):
        out["warnings"].append(f"duplicate MAC {m} in both files: {macs_of['dynamic'][m]}, {macs_of['static'][m]}")
    return out
