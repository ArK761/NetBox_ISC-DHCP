"""Generated files stored for the DHCP server. Only what changed is recomputed; dhcpd.conf includes come from the stored set."""
import hashlib
import ipaddress

from django.db import transaction
from django.utils import timezone

from . import audit
from .models import ExportFile


def _put(key, area, path, text):
    """Store (or update) one file; returns True when its content changed."""
    sha = hashlib.sha256(text.encode()).hexdigest()
    row = ExportFile.objects.filter(key=key).first()
    if row and row.sha256 == sha and row.path == path:
        return False
    for other in ExportFile.objects.filter(path=path).exclude(key=key):
        _del(other)
    audit.record(path, "update" if row else "add", row.content if row else "", text, row.sha256 if row else "", sha)
    if row is None:
        row = ExportFile(key=key)
    row.area, row.path, row.content, row.sha256, row.size, row.updated = area, path, text, sha, len(text.encode()), timezone.now()
    row.save()
    return True


def _del(row):
    audit.record(row.path, "delete", row.content, "", row.sha256, "")
    row.delete()


def _drop(**flt):
    rows = list(ExportFile.objects.filter(**flt))
    for r in rows:
        _del(r)
    return bool(rows)


# ---- TABLE ------------------------------------------------------------------------------------------
def _tables_state():
    from ..hosts.logic import get_model
    from ..hosts.models import HostConfig
    from ..models import settings_obj

    st, cfg = settings_obj(), HostConfig.objects.first()
    if cfg is None or not cfg.include_tables or not (st and st.table_dir):
        return None, None, None
    gm = get_model(cfg.group_model)
    return (cfg, st, gm) if gm is not None else (None, None, None)


def regen_group(hg, state=None):
    """Both files of one group. Not stored (and removed) when the group is not included, empty or failing."""
    from ..hosts.codegen import render_files
    from ..hosts.logic import _SAFE_NAME, build_group
    from ..services import is_safe_name

    cfg, st, gm = state or _tables_state()
    changed = False
    keep = set()
    if cfg is not None and hg.group_model == cfg.group_model and gm.objects.filter(pk=hg.group_pk).exists() \
            and (not cfg.include_each or hg.include) and _SAFE_NAME.match(hg.name or ""):
        rendered = render_files(hg, build_group(hg), {k: hg.code(k) for k in ("dynamic", "static")})
        for kind in ("dynamic", "static"):
            text, err = rendered[kind]
            name = hg.file_name(kind)
            if err or not text.strip() or not is_safe_name(name):
                continue
            key = f"group:{hg.pk}:{kind}"
            keep.add(key)
            changed |= _put(key, "table", f"{st.table_dir.path}/{name}", text)
    for row in ExportFile.objects.filter(key__startswith=f"group:{hg.pk}:"):
        if row.key not in keep:
            _del(row)
            changed = True
    return changed


def regen_tables():
    from ..hosts.models import HostGroup

    state = _tables_state()
    changed = False
    seen = set()
    for hg in HostGroup.objects.all():
        changed |= regen_group(hg, state)
        seen.add(hg.pk)
    for row in ExportFile.objects.filter(area="table"):
        if int(row.key.split(":")[1]) not in seen:
            _del(row)
            changed = True
    return changed


# ---- SUBNET -----------------------------------------------------------------------------------------
def _subnet_plan():
    """{prefix pk: (prefix obj, pool, code)} of every subnet that is included (pool on, per-pool switch)."""
    from ..models import PoolTemplate, SubnetConfig, SubnetOverride
    from ..source_fields import _field_q
    from ..views import _pool_info, _pool_names

    cfg = SubnetConfig.objects.first()
    if cfg is None or not cfg.include_subnets:
        return {}
    model, qs, key = _pool_info(cfg)
    if model is None or key is None:
        return {}
    pools = {p.name: p for p in PoolTemplate.objects.all()}
    ovr = {(o.pool_id, o.prefix_id): o for o in SubnetOverride.objects.all()}
    plan = {}
    for value, name in _pool_names(model, qs, key):
        pt = pools.get(name)
        if pt is None or not pt.enabled or (cfg.include_each and not pt.include):
            continue
        for obj in qs.filter(_field_q(model, key["field"], [value])):
            o = ovr.get((pt.pk, obj.pk)) if pt.allow_override else None
            plan[obj.pk] = (obj, pt, o.code if o is not None else pt.template, o is not None)
    return plan


def _render_subnet(obj, pt, code, own, args):
    from ..subnet_render import render_subnet

    pfx = str(getattr(obj, "prefix", ""))
    plen = getattr(getattr(obj, "prefix", None), "prefixlen", None)
    if not own:
        lo, hi = pt.allowed_range()
        if lo is None or plen is None or not lo <= plen <= hi:
            return pfx, None
    text, errs = render_subnet(code, pfx, args["dns"], {"obj": obj, "cf": getattr(obj, "custom_field_data", {}) or {}},
                               gateway_mode=args["gateway_mode"], snippets=args["snippets"], site=args["site"],
                               known_classes=args["known_classes"], invalid=args["invalid"])
    return pfx, (None if errs or not text.strip() else text)


def _args():
    from ..compat import _render_args
    from ..models import DNSServer

    a = _render_args()
    a["dns"] = list(DNSServer.objects.filter(active=True).values_list("ip", flat=True))
    return a


def regen_subnets(prefix_pks=None, pool_pk=None):
    """All subnets, only the given prefix objects (pks), or only one pool (+ stale rows)."""
    from ..base_config import subnet_includes
    from ..models import settings_obj

    st = settings_obj()
    plan = _subnet_plan() if st and st.subnet_dir else {}
    args = _args() if plan else None
    changed = False
    if pool_pk is not None:
        todo = [p for p, v in plan.items() if v[1].pk == pool_pk]
    else:
        todo = plan.keys() if prefix_pks is None else [p for p in prefix_pks if p in plan]
    keep = set()
    for pk in todo:
        obj, pt, code, own = plan[pk]
        pfx, text = _render_subnet(obj, pt, code, own, args)
        inc = subnet_includes([pfx])
        if text is None or not inc:
            continue
        key = f"subnet:{pk}"
        keep.add(key)
        changed |= _put(key, "subnet", f"{st.subnet_dir.path}/{inc[0].file}", text)
    rows = ExportFile.objects.filter(area="subnet")
    if pool_pk is not None:  # this pool's subnets + rows whose subnet is no longer in any included pool
        stale = {f"subnet:{p}" for p in todo} | {r.key for r in rows if int(r.key.split(":")[1]) not in plan}
        rows = rows.filter(key__in=stale)
    elif prefix_pks is not None:
        rows = rows.filter(key__in=[f"subnet:{p}" for p in prefix_pks])
    for row in rows:
        if row.key not in keep:
            _del(row)
            changed = True
    return changed


# ---- dhcpd.conf -------------------------------------------------------------------------------------
def _net_key(path):
    name = path.rsplit("/", 1)[-1].removesuffix("_CFG")
    try:
        return (0, int(ipaddress.ip_address(name)))
    except ValueError:
        return (1, 0)


def stored_includes():
    """(table paths, subnet paths) in include order = exactly the stored files."""
    t = list(ExportFile.objects.filter(area="table").order_by("path").values_list("path", flat=True))
    s = sorted(ExportFile.objects.filter(area="subnet").values_list("path", flat=True), key=_net_key)
    return t, s


def regen_conf():
    from ..models import BaseConfig, settings_obj

    st, cfg = settings_obj(), BaseConfig.objects.first()
    if cfg is None or not (st and st.config_path):
        return _drop(area="conf")
    from ..services import build_base_config

    text = build_base_config(cfg)[0]
    path = f"{st.config_path.rstrip('/')}/{cfg.name}"
    for other in ExportFile.objects.filter(area="conf").exclude(path=path):
        _del(other)
    return _put("conf", "conf", path, text)


def regen_all(cause="regenerate all", always=True):
    audit.start()
    with transaction.atomic():
        regen_tables()
        regen_subnets()
        regen_conf()
    return audit.finish(cause, always=always)


def manifest_hash():
    rows = ExportFile.objects.order_by("area", "path").values_list("path", "sha256")
    return hashlib.sha256("".join(f"{p} {s}\n" for p, s in rows).encode()).hexdigest()


def manifest():
    rows = list(ExportFile.objects.order_by("area", "path").values("path", "area", "sha256", "size", "updated"))
    total = hashlib.sha256("".join(f"{r['path']} {r['sha256']}\n" for r in rows).encode()).hexdigest()
    dirs = sorted({r["path"].rsplit("/", 1)[0] for r in rows if r["area"] != "conf"})
    return {"hash": total, "count": len(rows), "dirs": dirs,
            "files": [{"path": r["path"], "area": r["area"], "sha256": r["sha256"], "size": r["size"],
                       "updated": r["updated"].isoformat()} for r in rows]}
