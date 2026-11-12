"""Hosts: read groups (DHCP classes) and MAC/IP objects from any NetBox object type."""
from django.db import models
from django.db.models import Q
from extras.models import CustomField

from ..dhcp_tables import _SAFE_NAME, natural_key, prepare
from ..source_fields import _custom_field, build_q, distinct_values, field_options, get_model, is_active, label_for

MAX_MAC_FIELDS = 3


def link_candidates(mac_model, group_model) -> list[tuple[str, str]]:
    """Fields of the MAC object that point to the group object (foreign key or object custom field)."""
    if mac_model is None or group_model is None:
        return []
    out = []
    for f in mac_model._meta.get_fields():
        if getattr(f, "concrete", False) and f.is_relation and not f.many_to_many and f.related_model is group_model:
            out.append((f.name, str(f.verbose_name).capitalize()))
    for cf in CustomField.objects.get_for_model(mac_model):
        if cf.type == "object" and cf.related_object_type is not None and cf.related_object_type.model_class() is group_model:
            out.append((f"cf_{cf.name}", f"{cf.label or cf.name} (custom field)"))
    return out


def effective_link(cfg, mac_model, group_model) -> str:
    keys = [k for k, _ in link_candidates(mac_model, group_model)]
    if cfg.link_field in keys:
        return cfg.link_field
    return keys[0] if len(keys) == 1 else ""


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


def _group_q(link, group) -> Q:
    if link.startswith("cf_"):
        return Q(**{f"custom_field_data__{link[3:]}": group.pk})
    return Q(**{link: group})


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


def overview(cfg, open_row=None) -> dict:
    """Groups found (with their table name and whether they get tables) + per selected group:
    objects, hosts (dynamic / static), skipped, warnings."""
    gm, mm = get_model(cfg.group_model), get_model(cfg.mac_model)
    out = {"group_model": gm, "mac_model": mm, "groups": [], "rows": None, "link": "", "links": [], "need": []}
    conds = [c for c in cfg.group_conditions or [] if c.get("field")]
    active = [c for c in conds if is_active(c)]
    chosen = set(gm.objects.filter(build_q(gm, active)).values_list("pk", flat=True)) if gm is not None and active else set()
    out["conditions"] = condition_rows(gm, conds, open_row)
    if gm is not None:
        gkeys = {o["key"] for o in field_options(gm)}
        gname = cfg.group_name_field if cfg.group_name_field in gkeys else ""
        found = [{"obj": g, "name": name_of(g, gname), "selected": g.pk in chosen} for g in gm.objects.all()]
        for g in found:
            g["valid"] = bool(_SAFE_NAME.match(g["name"]))
        out["groups"] = sorted(found, key=lambda g: natural_key(g["name"]))
    if mm is not None:
        out["links"] = link_candidates(mm, gm)
        out["link"] = effective_link(cfg, mm, gm)
    keys = {o["key"] for o in field_options(mm)}
    macs = [k for k in cfg.mac_fields or [] if k in keys]
    if gm is None:
        out["need"].append("group_model")
    elif not any(g["selected"] for g in out["groups"]):
        out["need"].append("groups")
    if mm is None:
        out["need"].append("mac_model")
    else:
        if not out["link"]:
            out["need"].append("link")
        if not macs:
            out["need"].append("mac")
    if out["need"]:
        return out
    ip = cfg.ip_field if cfg.ip_field in keys else ""
    hname = cfg.host_name_field if cfg.host_name_field in keys else ""
    rows = []
    for g in out["groups"]:
        if not g["selected"]:
            continue
        raw = [(name_of(o, hname), [read_value(o, k) for k in macs], read_value(o, ip) if ip else None)
               for o in mm.objects.filter(_group_q(out["link"], g["obj"]))]
        dyn, st, warn = prepare(raw)
        rows.append({"group": g["obj"], "name": g["name"], "valid": g["valid"], "objects": len(raw), "dynamic": len(dyn),
                     "static": len(st), "hosts": sum(len(t.macs) for t in st),
                     "skipped": len(raw) - len(dyn) - len(st), "warnings": warn})
    out["rows"] = rows
    return out
