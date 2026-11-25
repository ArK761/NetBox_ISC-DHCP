"""New values on the Subnety page: a condition row (field + ticked values, mode include) has values that are neither
ticked nor marked 'Nepoužívať' (e.g. a new tenant group for POOL_TenantGroup). Shown in the warnings bar with the
number of prefixes that already have the value and what is missing (set it on prefixes / tick it on Subnety)."""
from django.core.cache import cache

CACHE_KEY = "isc_dhcp_newvalues"
SHOW = 20  # values listed per field (the rest is a count)


POOLS_KEY = "isc_dhcp_pools_off"


def invalidate(*args, **kwargs):
    cache.delete(CACHE_KEY)
    cache.delete(POOLS_KEY)


def _candidates(model, key):
    """Every possible value of the field: object custom fields = every object of that type (also unused ones)."""
    from .source_fields import _custom_field, distinct_values

    cf = _custom_field(model, key) if key.startswith("cf_") else None
    if cf is not None and cf.type in ("object", "multiobject") and cf.related_object_type is not None:
        from .dhcp_tables import natural_key

        related = cf.related_object_type.model_class()
        if related is None:
            return []
        return sorted(((str(o.pk), str(o)) for o in related.objects.all()[:2000]), key=lambda p: natural_key(p[1]))
    return distinct_values(model, key)


def compute():
    """[{index, field, label, pool_key, rows: [(value, label, prefixes)], more}] for every row with new values."""
    from .models import SubnetConfig
    from .source_fields import _field_q, build_q, cond_values, get_model, label_for

    cfg = SubnetConfig.objects.first()
    model = get_model(cfg.source_model) if cfg else None
    if model is None:
        return []
    conds = [c for c in cfg.conditions or []]
    out = []
    for i, c in enumerate(conds):
        if not c.get("field") or c.get("all") or c.get("mode", "include") == "exclude":
            continue  # all values / exclude mode: a new value is already used
        chosen = set(cond_values(c))
        if not chosen:
            continue  # nothing ticked = the row does not filter
        skip = chosen | {str(v) for v in c.get("ignored") or []}
        new = [(v, lbl) for v, lbl in _candidates(model, c["field"]) if v not in skip]
        if not new:
            continue
        others = [x for j, x in enumerate(conds) if j != i]
        base = model.objects.filter(build_q(model, others))
        rows = [(v, lbl, base.filter(_field_q(model, c["field"], [v])).count()) for v, lbl in new[:SHOW]]
        out.append({"index": i, "field": c["field"], "label": label_for(model, c["field"]), "pool_key": bool(c.get("pool_key")),
                    "rows": rows, "more": max(0, len(new) - SHOW)})
    return out


def new_values():
    data = cache.get(CACHE_KEY)
    if data is None:
        try:
            data = compute()
        except Exception:
            data = []
        cache.set(CACHE_KEY, data, 60)  # tenant groups etc. are not watched: a new object shows within a minute
    return data


def notices():
    """Warnings bar entries (level info): one per new value, with the 'Nepoužívať' action."""
    from django.urls import reverse

    from .i18n import t
    from .models import SubnetConfig

    data = new_values()
    if not data:
        return []
    cfg = SubnetConfig.objects.first()
    url = cfg.get_absolute_url() if cfg else reverse("plugins:netbox_isc_dhcp:subnetconfig_list")
    post = reverse("plugins:netbox_isc_dhcp:subnetconfig_inline", kwargs={"pk": cfg.pk}) if cfg else ""
    out = []
    for f in data:
        for value, lbl, n in f["rows"]:
            text = t("nv.zero" if n == 0 else "nv.some", field=f["label"], value=lbl, n=n)
            action = (post, {"field": "cond_ignore", "index": str(f["index"]), "value": value}, t("nv.ignore"))
            out.append(("info", "mdi-new-box", text, url, t("menu.subnets"), None, action))
        if f["more"]:
            out.append(("info", "mdi-new-box", t("nv.more", field=f["label"], n=f["more"]), url, t("menu.subnets")))
    return out


def pools_off():
    """[(pool name, subnets)] of pools that HAVE subnets but Generate is off (new pools start off) - not in the CFG."""
    data = cache.get(POOLS_KEY)
    if data is not None:
        return data
    data = []
    try:
        from .models import PoolTemplate, SubnetConfig
        from .source_fields import _field_q
        from .views import _pool_info, _pool_names

        cfg = SubnetConfig.objects.first()
        model, qs, key = _pool_info(cfg) if cfg else (None, None, None)
        if key is not None:
            pools = {p.name: p for p in PoolTemplate.objects.all()}
            for value, name in _pool_names(model, qs, key):
                pt = pools.get(str(name)[:100])
                if pt is None or not pt.enabled:  # no pool yet (made on the Subnety page) or Generate off
                    n = qs.filter(_field_q(model, key["field"], [value])).count()
                    if n:
                        data.append((pt.name if pt else str(name), n))
    except Exception:
        data = []
    cache.set(POOLS_KEY, data, 60)
    return data


def pool_notices():
    from django.urls import reverse

    from .i18n import t
    from .models import SubnetConfig

    data = pools_off()
    if not data:
        return []
    cfg = SubnetConfig.objects.first()
    url = cfg.get_absolute_url() if cfg else reverse("plugins:netbox_isc_dhcp:subnetconfig_list")
    return [("warning", "mdi-pause-circle-outline", t("warn.pool_off", name=n, n=c), url, t("menu.subnets")) for n, c in data]
