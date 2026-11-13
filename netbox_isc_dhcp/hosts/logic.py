"""Hosts: read groups (DHCP classes) and MAC/IP objects from any NetBox object type."""
from django.db import models

from ..dhcp_tables import _SAFE_NAME, natural_key, normalize_ip, normalize_mac
from ..source_fields import _custom_field, build_q, distinct_values, field_options, get_model, is_active, label_for

MAX_HOSTS = 3


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
    """One source for the page: object, conditions, host rows, what is still missing."""
    mm = get_model(src.model)
    keys = {o["key"] for o in field_options(mm)}
    conds = [c for c in src.conditions or [] if c.get("field")]
    need = []
    if mm is None:
        need.append("model")
    else:
        if not any(is_active(c) for c in conds):
            need.append("cond")
        if not host_rows(src, keys):
            need.append("mac")
    return {"src": src, "model": mm, "need": need, "conditions": condition_rows(mm, conds, open_row) if mm else []}


def host_rows(src, keys) -> list[dict]:
    """Usable host rows of a source: MAC field exists; IP field exists or is empty."""
    out = []
    for r in (src.hosts or [])[:MAX_HOSTS]:
        if r.get("mac") in keys and (not r.get("ip") or r["ip"] in keys):
            hn = r.get("hn") or "name"
            out.append({"mac": r["mac"], "ip": r.get("ip") or "", "dyn": bool(r.get("dyn")),
                        "hn": hn if hn in ("name", "host", "none") or hn in keys else "name"})
    return out


def _empty(v):
    return v in (None, "")


def build_group(hg) -> dict:
    """Both files of a group from all its sources.
    dynamic rows: (host, mac, object name); static rows: (host, mac, ip, object name);
    lost: hosts that do not get into DHCP (host, reason, value); warnings: duplicate MAC / IP (never a reason to leave out)."""
    dyn, sta, lost, bad_ip = [], [], [], []
    objects, configured = 0, 0
    for src in hg.sources.all():
        info = source_info(src)
        if info["need"]:
            continue
        configured += 1
        mm, keys = info["model"], {o["key"] for o in field_options(info["model"])}
        rows = host_rows(src, keys)
        hname = src.host_name_field if src.host_name_field in keys else ""
        active = [c for c in src.conditions if c.get("field") and is_active(c)]
        for o in mm.objects.filter(build_q(mm, active)):
            objects += 1
            base = name_of(o, hname)
            if not _SAFE_NAME.match(base):
                lost.append((base, "bad_name", ""))
                continue
            any_mac, own = False, []
            for idx, r in enumerate(rows, 1):
                host = base if len(rows) == 1 else f"{base}_{idx}"
                mv = read_value(o, r["mac"])
                ipv = read_value(o, r["ip"]) if r["ip"] else None
                if _empty(mv):
                    if r["ip"] and not _empty(ipv):  # IP without its MAC
                        own.append((host, "no_mac", ""))
                    continue
                any_mac = True
                m = normalize_mac(mv)
                if m is None:
                    own.append((host, "bad_mac", str(mv)))
                    continue
                if not r["ip"]:
                    dyn.append((host, m, base))
                    continue
                ip = None if _empty(ipv) else normalize_ip(ipv)
                if ip is None:  # no (valid) IP: cannot be static; only "also into class" puts it into the dynamic file
                    if r["dyn"]:
                        dyn.append((host, m, base))
                        if not _empty(ipv):
                            bad_ip.append(f"{host}: invalid IP '{ipv}', host only in the dynamic file")
                    else:
                        own.append((host, "no_ip" if _empty(ipv) else "bad_ip", "" if _empty(ipv) else str(ipv)))
                    continue
                hn = r["hn"]
                if hn in ("name", "host", "none"):
                    hostname = {"name": base, "host": host, "none": None}[hn]
                else:  # value of another field (empty -> no option host-name)
                    v = read_value(o, hn)
                    hostname = None if _empty(v) else str(v).strip()
                    if hostname and not _SAFE_NAME.match(hostname):
                        bad_ip.append(f"{host}: host-name '{hostname}' has characters not allowed, option host-name left out")
                        hostname = None
                sta.append((host, m, ip, base, hostname))
                if r["dyn"]:
                    dyn.append((host, m, base))
            if not any_mac and not own:
                own.append((base, "no_mac", ""))
            lost += own
    dyn.sort(key=lambda r: natural_key(r[0]))
    sta.sort(key=lambda r: natural_key(r[0]))
    static, seen = [], set()
    for r in sta:  # dhcpd refuses two host blocks with the same name
        if r[0] in seen:
            lost.append((r[0], "dup_name", ""))
            continue
        seen.add(r[0])
        static.append(r)
    warnings = list(bad_ip)
    for kind, rows in (("dynamic", dyn), ("static", static)):
        owners = {}
        for r in rows:
            owners.setdefault(r[1], []).append(r[0])
        for m, names in owners.items():
            if len(set(names)) > 1:
                warnings.append(f"{hg.file_name(kind)}: duplicate MAC {m}: {', '.join(names)}")
    ips = {}
    for r in static:
        ips.setdefault(r[2], []).append(r[0])
    for i, names in ips.items():
        if len(names) > 1:
            warnings.append(f"{hg.file_name('static')}: duplicate IP {i}: {', '.join(names)}")
    dobj, sobj = {}, {}
    for r in dyn:
        dobj.setdefault(r[1], set()).add(r[2])
    for r in static:
        sobj.setdefault(r[1], set()).add(r[3])
    for m in sorted(set(dobj) & set(sobj)):
        if dobj[m] != sobj[m]:  # the same MAC of different objects (own MAC in both files is wanted)
            warnings.append(f"duplicate MAC {m} in both files: {', '.join(sorted(dobj[m] | sobj[m], key=natural_key))}")
    lost.sort(key=lambda r: natural_key(r[0]))
    counts = {}
    for _, reason, _ in lost:
        counts[reason] = counts.get(reason, 0) + 1
    srcs = list(hg.sources.all())
    return {"objects": objects, "configured": configured, "has_sources": bool(srcs),
            "dynamic": {"rows": dyn, "macs": len(dyn)}, "static": {"rows": static, "macs": len(static)},
            "lost": lost, "lost_counts": counts, "skipped": len(lost), "warnings": warnings,
            "source_labels": sorted({str(get_model(x.model)._meta.verbose_name).capitalize() for x in srcs if get_model(x.model)}),
            "source_count": len(srcs)}
