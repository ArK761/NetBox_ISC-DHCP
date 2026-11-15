"""Recompute only the stored files a change touches (once per transaction), then dhcpd.conf."""
import logging
import threading

from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save

log = logging.getLogger("netbox_isc_dhcp.export")
_local = threading.local()


def _new():
    return {"groups": set(), "tables": False, "subnets": set(), "all_subnets": False, "pools": set(), "conf": False, "causes": []}


def _flush():
    p, _local.p = getattr(_local, "p", None) or _new(), None
    from . import audit, build
    from ..hosts.models import HostGroup

    audit.start()
    try:
        if p["tables"]:
            build.regen_tables()
        else:
            state = build._tables_state()
            for hg in HostGroup.objects.filter(pk__in=p["groups"]):
                build.regen_group(hg, state)
            gone = [k for k in p["groups"] if not HostGroup.objects.filter(pk=k).exists()]
            for k in gone:
                for row in build.ExportFile.objects.filter(key__startswith=f"group:{k}:"):
                    build._del(row)
        if p["all_subnets"]:
            build.regen_subnets()
        else:
            for pool in p["pools"]:
                build.regen_subnets(pool_pk=pool)
            if p["subnets"]:
                build.regen_subnets(list(p["subnets"]))
        build.regen_conf()
        causes = list(dict.fromkeys(p["causes"]))
        audit.finish("; ".join(causes[:20]) + (f" … +{len(causes) - 20}" if len(causes) > 20 else ""))
    except Exception:  # never break a NetBox save because of the export
        log.exception("export regeneration failed")


def mark(**kw):
    """Collect what to recompute; flushed once when the transaction commits (at once outside a transaction)."""
    p = getattr(_local, "p", None)
    new = p is None
    if new:
        p = _local.p = _new()
    for k, v in kw.items():
        if k == "cause":
            p["causes"].append(v)
            continue
        if isinstance(p[k], set):
            p[k] |= set(v)
        else:
            p[k] = p[k] or v
    if new:
        transaction.on_commit(_flush)


# ---- host source objects (any NetBox model a HostSource uses) --------------------------------------
def _source_models():
    res = cache.get("isc_dhcp_src_models")
    if res is None:
        from ..hosts.models import HostSource

        res = set(HostSource.objects.exclude(model="").values_list("model", flat=True))
        cache.set("isc_dhcp_src_models", res, 300)
    return res


def _groups_with(instance, label):
    from ..hosts.logic import get_model
    from ..hosts.models import HostSource
    from ..source_fields import build_q
    from ..source_fields import is_active

    out = set()
    for src in HostSource.objects.filter(model=label):
        mm = get_model(label)
        active = [c for c in src.conditions if c.get("field") and is_active(c)]
        if active and mm.objects.filter(build_q(mm, active)).filter(pk=instance.pk).exists():
            out.add(src.group_id)
    return out


def _cause(sender, instance, kw):
    from ..i18n import t

    key = "aud.c_deleted" if kw.get("signal") is post_delete else "aud.c_saved"
    return t(key, what=str(sender._meta.verbose_name), name=str(instance))


def _label(sender):
    return f"{sender._meta.app_label}.{sender._meta.model_name}"


def obj_before(sender, instance, raw=False, **kwargs):
    if raw or sender._meta.app_label == "netbox_isc_dhcp" or not instance.pk or _label(sender) not in _source_models():
        return
    instance._isc_groups_before = _groups_with(instance, _label(sender))


def obj_after(sender, instance, raw=False, **kwargs):
    if raw or sender._meta.app_label == "netbox_isc_dhcp" or _label(sender) not in _source_models():
        return
    before = getattr(instance, "_isc_groups_before", set())
    after = set() if kwargs.get("signal") is post_delete else _groups_with(instance, _label(sender))
    if before | after:
        mark(groups=before | after, cause=_cause(sender, instance, kwargs))


pre_save.connect(obj_before, dispatch_uid="isc_dhcp_export_obj_pre")
pre_delete.connect(obj_before, dispatch_uid="isc_dhcp_export_obj_predel")
post_save.connect(obj_after, dispatch_uid="isc_dhcp_export_obj_post")
post_delete.connect(obj_after, dispatch_uid="isc_dhcp_export_obj_postdel")


# ---- plugin objects ---------------------------------------------------------------------------------
def _connect():
    from ipam.models import Prefix

    from ..hosts.models import HostCodeTemplate, HostConfig, HostGroup, HostGroupCode, HostSource
    from ..models import BaseConfig, ConfigVariable, DHCPPath, DNSServer, PluginSettings, PoolTemplate, SubnetConfig, SubnetOverride

    def on(models, fn, name):
        for m in models:
            post_save.connect(fn, sender=m, weak=False, dispatch_uid=f"isc_dhcp_exp_{name}_s_{m.__name__}")
            post_delete.connect(fn, sender=m, weak=False, dispatch_uid=f"isc_dhcp_exp_{name}_d_{m.__name__}")

    def raw_ok(kw):
        return not kw.get("raw")

    def c(sender, instance, kw):
        return _cause(sender, instance, kw)

    on([HostConfig, HostCodeTemplate], lambda sender, instance, **kw: raw_ok(kw) and mark(tables=True, cause=c(sender, instance, kw)), "tables")
    on([PluginSettings, DHCPPath], lambda sender, instance, **kw: raw_ok(kw) and mark(tables=True, all_subnets=True, cause=c(sender, instance, kw)), "paths")
    on([HostGroup], lambda sender, instance, **kw: raw_ok(kw) and mark(groups=[instance.pk], cause=c(sender, instance, kw)), "group")
    on([HostSource, HostGroupCode], lambda sender, instance, **kw: raw_ok(kw) and mark(groups=[instance.group_id], cause=c(sender, instance, kw)), "groupparts")

    def src_changed(sender, instance, **kw):
        cache.delete("isc_dhcp_src_models")
    on([HostSource], src_changed, "srcmodels")
    on([SubnetConfig, DNSServer, ConfigVariable], lambda sender, instance, **kw: raw_ok(kw) and mark(all_subnets=True, cause=c(sender, instance, kw)), "subnets")
    on([PoolTemplate], lambda sender, instance, **kw: raw_ok(kw) and mark(pools=[instance.pk], cause=c(sender, instance, kw)), "pool")
    on([SubnetOverride], lambda sender, instance, **kw: raw_ok(kw) and mark(subnets=[instance.prefix_id], cause=c(sender, instance, kw)), "override")
    on([Prefix], lambda sender, instance, **kw: raw_ok(kw) and mark(subnets=[instance.pk], cause=c(sender, instance, kw)), "prefix")
    on([BaseConfig], lambda sender, instance, **kw: raw_ok(kw) and mark(conf=True, cause=c(sender, instance, kw)), "conf")


_connect()


def _after_migrate(sender, **kwargs):
    """First fill (and refresh after every plugin update) so includes never point to missing files."""
    if getattr(sender, "name", "") != "netbox_isc_dhcp":
        return
    try:
        from . import build
        build.regen_all(cause=__import__("netbox_isc_dhcp.i18n", fromlist=["t"]).t("aud.c_migrate"), always=False)
    except Exception:
        log.exception("export regeneration after migrate failed")


from django.db.models.signals import post_migrate  # noqa: E402

post_migrate.connect(_after_migrate, dispatch_uid="isc_dhcp_export_migrate")
