"""Hosts: read groups (DHCP classes) and MAC/IP objects from any NetBox object type."""
from django.db import models
from django.db.models import Q
from extras.models import CustomField

from ..dhcp_tables import natural_key, prepare
from ..source_fields import _custom_field, field_options, get_model

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


def _group_q(link, group) -> Q:
    if link.startswith("cf_"):
        return Q(**{f"custom_field_data__{link[3:]}": group.pk})
    return Q(**{link: group})


def overview(cfg) -> dict:
    """Groups found + per group: objects, hosts (dynamic / static), skipped, warnings."""
    gm, mm = get_model(cfg.group_model), get_model(cfg.mac_model)
    out = {"group_model": gm, "mac_model": mm, "groups": [], "rows": None, "link": "", "links": [], "need": []}
    if gm is not None:
        out["groups"] = sorted(gm.objects.all(), key=lambda g: natural_key(str(g)))
    if mm is None:
        return out
    out["links"] = link_candidates(mm, gm)
    out["link"] = effective_link(cfg, mm, gm)
    keys = {o["key"] for o in field_options(mm)}
    macs = [k for k in cfg.mac_fields or [] if k in keys]
    if gm is None:
        out["need"].append("group_model")
    if not out["link"]:
        out["need"].append("link")
    if not macs:
        out["need"].append("mac")
    if out["need"]:
        return out
    ip = cfg.ip_field if cfg.ip_field in keys else ""
    rows = []
    for g in out["groups"]:
        raw = [(str(o), [read_value(o, k) for k in macs], read_value(o, ip) if ip else None)
               for o in mm.objects.filter(_group_q(out["link"], g))]
        dyn, st, warn = prepare(raw)
        rows.append({"group": g, "objects": len(raw), "dynamic": len(dyn), "static": len(st),
                     "hosts": sum(len(t.macs) for t in st), "skipped": len(raw) - len(dyn) - len(st), "warnings": warn})
    out["rows"] = rows
    return out
