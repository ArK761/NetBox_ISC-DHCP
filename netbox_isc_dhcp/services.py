"""Glue between NetBox data and the pure generators."""
import hashlib

from django.utils import timezone
from ipam.models import IPAddress, Prefix
from tenancy.models import Tenant

from .base_config import is_safe_name, render_base_config
from .dhcp_tables import FileResult, build_file
from extras.models import CustomField

from .i18n import t
from .models import BaseConfig, SubnetConfig, DHCPFile, base_path, settings_obj


def dhcp_prefixes(cfg) -> list[str]:
    """Prefixes of the chosen object that match all conditions (nothing when no object/condition is set)."""
    from .source_fields import build_q, get_model

    model = get_model(cfg.source_model)
    if model is None or "prefix" not in {f.name for f in model._meta.get_fields()} or not [c for c in cfg.conditions if c.get("field") and c.get("value", "") != ""]:
        return []
    return [str(p) for p in model.objects.filter(build_q(model, cfg.conditions)).values_list("prefix", flat=True)]


def table_includes() -> tuple[list[str], list[str]]:
    """Full paths of the group files (<name>_Dynamic, <name>_Static) when 'include into dhcpd.conf' is ticked on Hosty."""
    from .hosts.codegen import render_files
    from .hosts.logic import _SAFE_NAME, build_group, get_model
    from .hosts.models import HostConfig, HostGroup

    st, cfg = settings_obj(), HostConfig.objects.first()
    if cfg is None or not cfg.include_tables:
        return [], []
    if not (st and st.table_dir):
        return [], [t("warn.no_table_dir", n=1)]
    gm = get_model(cfg.group_model)
    if gm is None:
        return [], []
    live = set(gm.objects.values_list("pk", flat=True))
    paths, bad = [], []
    for hg in HostGroup.objects.filter(group_model=cfg.group_model).order_by("name"):
        if hg.group_pk not in live or (cfg.include_each and not hg.include):
            continue
        rendered = render_files(hg, build_group(hg), {k: hg.code(k) for k in ("dynamic", "static")})
        for kind in ("dynamic", "static"):
            name = hg.file_name(kind)
            text, err = rendered[kind]
            if err or not text.strip():  # owner: an empty (or failing) file is never included
                continue
            if _SAFE_NAME.match(hg.name or "") and is_safe_name(name):
                paths.append(f"{st.table_dir.path}/{name}")
            else:
                bad.append(name)
    return paths, ([t("warn.bad_names", names=", ".join(bad))] if bad else [])


def subnet_prefixes() -> list[str]:
    """Prefixes whose <network>_CFG file is included: pools with Generate on, compatible subnets only."""
    from . import compat
    from .models import PoolTemplate, SubnetConfig
    from .source_fields import _field_q
    from .views import _pool_info, _pool_names

    cfg = SubnetConfig.objects.first()
    if cfg is None or not cfg.include_subnets:
        return []
    model, qs, key = _pool_info(cfg)
    if model is None or key is None:
        return []
    bad = {x["prefix"] for x in compat.incompatible()}
    pools = {p.name: p for p in PoolTemplate.objects.all()}
    out = []
    for value, name in _pool_names(model, qs, key):
        pt = pools.get(name)
        if pt is None or not pt.enabled or (cfg.include_each and not pt.include):
            continue
        for obj in qs.filter(_field_q(model, key["field"], [value])):
            pfx = str(getattr(obj, "prefix", ""))
            if pfx and pfx not in bad:
                out.append(pfx)
    return out


def subnet_includes_paths() -> tuple[list[str], list[str]]:
    from .base_config import subnet_includes

    st = settings_obj()
    pfx = subnet_prefixes()
    if not pfx:
        return [], []
    if not (st and st.subnet_dir):
        return [], [t("warn.no_subnet_dir")]
    return [f"{st.subnet_dir.path}/{i.file}" for i in subnet_includes(pfx)], []


def build_base_config(cfg: BaseConfig) -> tuple[str, list[str]]:
    """Return (dhcpd.conf text, warnings)."""
    st = settings_obj()
    tables, warnings = table_includes()
    if not base_path():
        warnings.insert(0, t("warn.no_base_path"))
    subs, w2 = subnet_includes_paths()
    warnings += w2
    st_dir = st.subnet_dir.path if st and st.subnet_dir and subs else ""
    text = render_base_config(cfg.static_text, tables, subnet_prefixes() if subs else [], subnet_dir=st_dir)
    return text, warnings


def _ip_value(value):
    """IP custom field: text value, or the pk of an IP address object."""
    if isinstance(value, int):
        obj = IPAddress.objects.filter(pk=value).first()
        return str(obj.address.ip) if obj else None
    return value


def file_content(f: DHCPFile) -> FileResult:
    """Generate one file from the tenants of its group."""
    raw = []
    for t in Tenant.objects.filter(group=f.group.group):
        cf = t.custom_field_data or {}
        ip = _ip_value(cf.get(f.ip_field)) if f.ip_field else None
        raw.append((t.name, [cf.get(m) for m in f.mac_fields], ip))
    return build_file(f.group.group.name, raw, f.template)


def regenerate_file(f: DHCPFile) -> bool:
    """Generate the file and store it. Returns True when the content changed (new hash)."""
    res = file_content(f)
    sha = hashlib.sha256(res.text.encode("utf-8")).hexdigest()
    changed = sha != f.sha256
    values = {"content": res.text, "sha256": sha, "warnings": res.warnings}
    if changed or f.generated is None:
        values["generated"] = timezone.now()
    DHCPFile.objects.filter(pk=f.pk).update(**values)  # update(): no signals, no loops
    for k, v in values.items():
        setattr(f, k, v)
    return changed


def variable_snippets() -> dict[str, str]:
    """name -> ISC lines of every variable that has a valid value."""
    from .models import ConfigVariable
    from .variables import VariableError

    out = {}
    for v in ConfigVariable.objects.all():
        try:
            out[v.name] = v.lines()
        except VariableError:
            pass
    return out


def variable_usage() -> dict[str, list[str]]:
    """name -> where it is used (pool code and group files with a `USE <name>` line)."""
    from .models import PoolTemplate
    from .variables import used_names

    usage: dict[str, list[str]] = {}
    for pt in PoolTemplate.objects.only("name", "template"):
        for n in used_names(pt.template):
            usage.setdefault(n, []).append(f"pool {pt.name}")
    for f in DHCPFile.objects.only("name", "template"):
        for n in used_names(f.template):
            usage.setdefault(n, []).append(f"file {f.name}")
    from .models import SubnetOverride

    for o in SubnetOverride.objects.select_related("pool"):
        for n in used_names(o.code):
            usage.setdefault(n, []).append(f"subnet {o.prefix_text} ({o.pool.name})")
    return usage


def invalid_variables() -> set[str]:
    """Names of variables that exist but have no valid value yet."""
    from .models import ConfigVariable

    return {v.name for v in ConfigVariable.objects.all()} - set(variable_snippets())


def check_context() -> dict:
    """Site knowledge for code checks: custom options, set variables and classes (static part + tenant tables)."""
    import re as _re

    from .isc_rules import site_definitions

    cfg = BaseConfig.objects.first()
    site = site_definitions(cfg.static_text if cfg else "")
    classes = set(site["classes"])
    for content in DHCPFile.objects.values_list("content", flat=True):
        classes |= set(_re.findall(r'\bclass\s+"([^"]+)"', content or ""))
    return {"site": site, "known_classes": classes, "invalid": invalid_variables()}
