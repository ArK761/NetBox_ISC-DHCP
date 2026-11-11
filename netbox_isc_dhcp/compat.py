"""Which subnets fit their pool: prefix size within the pool's range and code that renders without errors.
Incompatible subnets are never exported; the plugin shows them in red."""
from django.core.cache import cache

CACHE_KEY = "netbox_isc_dhcp_incompatible_v1"
LENGTHS = range(16, 31)


class _Any(dict):
    """Stand-in for obj / cf when testing the code on synthetic prefixes: every attribute is an empty text."""

    def __missing__(self, key):
        return ""

    def __getattr__(self, key):
        return ""


def invalidate(*args, **kwargs):
    cache.delete(CACHE_KEY)


def _render_args():
    from .models import DNSServer, SubnetConfig
    from .services import check_context, variable_snippets

    cfg = SubnetConfig.objects.first()
    return {
        "dns": list(DNSServer.objects.filter(active=True).values_list("ip", flat=True)) or ["10.0.0.1"],
        "gateway_mode": cfg.gateway_mode if cfg else "first",
        "snippets": variable_snippets(),
        **check_context(),
    }


def suitable_lengths(code: str, args=None) -> list[int]:
    """Prefix lengths (/16../30) the code renders on without any error."""
    from .subnet_render import render_subnet

    args = args or _render_args()
    out = []
    for n in LENGTHS:
        # only size-related errors decide the suitable sizes (classes, words... are reported separately)
        _, errs = render_subnet(code, f"10.0.0.0/{n}", args["dns"], {"obj": _Any(), "cf": _Any()},
                                gateway_mode=args["gateway_mode"], snippets=args["snippets"], lenient=True)
        if not errs:
            out.append(n)
    return out


def compute() -> list[dict]:
    """[{pool, pool_pk, prefix, reason}] for every subnet that does not fit its pool."""
    from .models import PoolTemplate, SubnetConfig
    from .source_fields import _field_q
    from .subnet_render import render_subnet
    from .views import _pool_info, _pool_names

    cfg = SubnetConfig.objects.first()
    if cfg is None:
        return []
    model, qs, key = _pool_info(cfg)
    if key is None or not any(c.get("field") for c in cfg.conditions or []):
        return []
    from .models import SubnetOverride

    args, out = _render_args(), []
    pools = {p.name: p for p in PoolTemplate.objects.all()}
    ovr = {(o.pool_id, o.prefix_id): o for o in SubnetOverride.objects.all()}
    for value, name in _pool_names(model, qs, key):
        pt = pools.get(name)
        if pt is None or not pt.enabled:
            continue
        if not pt.suitable:
            pt.suitable = suitable_lengths(pt.template, args)
            PoolTemplate.objects.filter(pk=pt.pk).update(suitable=pt.suitable)
        lo, hi = pt.allowed_range()
        for obj in qs.filter(_field_q(model, key["field"], [value]))[:5000]:
            pfx = str(getattr(obj, "prefix", ""))
            plen = getattr(getattr(obj, "prefix", None), "prefixlen", None)
            o = ovr.get((pt.pk, obj.pk)) if pt.allow_override else None
            if o is not None:  # individual code: its own check, no size range
                _, errs = render_subnet(o.code, pfx, args["dns"], {"obj": obj, "cf": getattr(obj, "custom_field_data", {}) or {}},
                                        gateway_mode=args["gateway_mode"], snippets=args["snippets"],
                                        site=args["site"], known_classes=args["known_classes"])
                if errs:
                    out.append({"pool": name, "pool_pk": pt.pk, "prefix": pfx, "prefix_pk": obj.pk, "reason": "individual code: " + errs[0]})
                continue
            if lo is None or plen is None or not lo <= plen <= hi:
                out.append({"pool": name, "pool_pk": pt.pk, "prefix": pfx, "prefix_pk": obj.pk,
                            "reason": f"size /{plen} is outside the range /{lo}-/{hi} of the pool" if lo else "the pool code has errors"})
                continue
            _, errs = render_subnet(pt.template, pfx, args["dns"], {"obj": obj, "cf": getattr(obj, "custom_field_data", {}) or {}},
                                    gateway_mode=args["gateway_mode"], snippets=args["snippets"],
                                    site=args["site"], known_classes=args["known_classes"])
            if errs:
                out.append({"pool": name, "pool_pk": pt.pk, "prefix": pfx, "prefix_pk": obj.pk, "reason": errs[0]})
    return out


def incompatible() -> list[dict]:
    res = cache.get(CACHE_KEY)
    if res is None:
        res = compute()
        cache.set(CACHE_KEY, res, 3600)
    return res


def ranges_text(lengths) -> str:
    """[16,17,...,26] -> '/16 – /26'; gaps are shown as separate parts."""
    if not lengths:
        return "—"
    parts, start, prev = [], lengths[0], lengths[0]
    for n in list(lengths[1:]) + [None]:
        if n is not None and n == prev + 1:
            prev = n
            continue
        parts.append(f"/{start}" if start == prev else f"/{start} – /{prev}")
        if n is not None:
            start = prev = n
    return ", ".join(parts)


def overrides() -> list[dict]:
    """Every individual subnet code with its state: active, or not used (pool disallows it / prefix gone / other pool)."""
    from .models import SubnetConfig, SubnetOverride
    from .source_fields import _field_q
    from .views import _pool_info, _pool_names

    cfg = SubnetConfig.objects.first()
    model, qs, key = _pool_info(cfg) if cfg else (None, None, None)
    in_pool = {}
    if key is not None:
        for value, name in _pool_names(model, qs, key):
            in_pool[name] = set(qs.filter(_field_q(model, key["field"], [value])).values_list("pk", flat=True))
    out = []
    for o in SubnetOverride.objects.select_related("pool"):
        state = "active"
        if not o.pool.allow_override:
            state = "disabled"
        elif o.prefix_id not in in_pool.get(o.pool.name, set()):
            state = "orphan"
        out.append({"obj": o, "state": state})
    return out
