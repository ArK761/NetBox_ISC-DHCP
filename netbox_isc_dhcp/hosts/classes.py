"""Dynamic classes as plugin objects (anti-mistake): a class used in subnet code (allow/deny members of "X")
cannot disappear (group delete, include off, own code without it), and renaming the group renames it everywhere."""
import re

from django.db import transaction

_MEMBERS = r'(\b(?:allow|deny|ignore)\s+members\s+of\s+"){}(")'


def used_classes() -> dict:
    """{class: [where, ...]} referenced by pool codes, individual subnet codes and the static part of dhcpd.conf."""
    from .usage import references

    out = {}
    for name, uses in references().items():
        out[name] = [u for u in uses]
    return out


def where_text(uses) -> str:
    from ..i18n import t

    parts = []
    for u in uses:
        if u["where"] == "pool":
            parts.append(t("cls.w_pool", name=u["name"]))
        elif u["where"] == "override":
            parts.append(t("cls.w_override", name=u["name"]))
        else:
            parts.append("dhcpd.conf")
    return ", ".join(dict.fromkeys(parts))


def _static_classes() -> set:
    from ..services import check_context

    return set(check_context()["site"].get("classes", ()))


def group_classes(hg, state=None) -> set:
    """Classes this group puts into dhcpd.conf (its _Dynamic/_Static files as they would be stored)."""
    from ..export.build import group_texts
    from .usage import defined_classes

    return {c for _, _, text in group_texts(hg, state).values() for c in defined_classes(text)}


def lost_by_group(hg_after, state=None) -> dict:
    """Used classes that would disappear when this group looks like hg_after (not saved yet): {class: uses}."""
    from ..export.models import ExportFile
    from ..services import dynamic_classes
    from .usage import defined_classes

    others = set()
    for content in ExportFile.objects.filter(area="table").exclude(key__startswith=f"group:{hg_after.pk}:").values_list("content", flat=True):
        others |= set(defined_classes(content))
    keep = others | _static_classes() | group_classes(hg_after, state)
    now = dynamic_classes()
    return {c: u for c, u in used_classes().items() if c in now and c not in keep}


def lost_by_tables(cfg_after) -> dict:
    """Used classes that would disappear with these table settings (HostConfig not saved yet)."""
    from ..export.build import _tables_state
    from ..services import dynamic_classes
    from .models import HostGroup

    cfg, st, gm = _tables_state()
    if cfg_after.include_tables and st is not None and getattr(st, "table_dir", None) and gm is not None:
        state = (cfg_after, st, gm)
        keep = set()
        for hg in HostGroup.objects.all():
            keep |= group_classes(hg, state)
    else:
        keep = set()
    keep |= _static_classes()
    now = dynamic_classes()
    return {c: u for c, u in used_classes().items() if c in now and c not in keep}


def refuse_text(lost: dict) -> str:
    from ..i18n import t

    return t("cls.refuse", items="; ".join(f'"{c}" ({where_text(u)})' for c, u in sorted(lost.items())))


def literal_lines(text) -> list:
    """Hand-written allow/deny members of "X" lines whose class X is dynamic: [(line no, mode, name)]."""
    from ..services import dynamic_classes

    dyn, out = dynamic_classes(), []
    for no, line in enumerate((text or "").split("\n"), 1):
        m = re.match(r'^\s*(allow|deny)\s+members\s+of\s+"([^"]+)"', line.split("#", 1)[0])
        if m and m.group(2) in dyn:
            out.append((no, m.group(1), m.group(2)))
    return out


def to_use(text) -> str:
    """Replace those lines by `USE ALLOW|DENY X` (with the class header line)."""
    from ..variables import CLASS_COMMENT

    lines, nos = (text or "").split("\n"), {no: (mode, name) for no, mode, name in literal_lines(text)}
    out = []
    for no, line in enumerate(lines, 1):
        if no in nos:
            mode, name = nos[no]
            indent = re.match(r"^[ \t]*", line).group(0)
            if not (out and out[-1].strip() == CLASS_COMMENT):
                out.append(indent + CLASS_COMMENT)
            out.append(f"{indent}USE {mode.upper()} {name}")
        else:
            out.append(line)
    return "\n".join(out)


def _r(new):
    def f(m):
        g = [x for x in m.groups()]
        for i in (0, 2, 4):
            if g[i] is not None:
                return g[i] + new + (g[i + 1] or "")
        return m.group(0)
    return f


def rename_class(old: str, new: str) -> list:
    """Rewrite allow/deny/ignore members of "old" to "new" in pools, individual subnet codes and the static part (atomic)."""
    from ..models import BaseConfig, PoolTemplate, SubnetOverride

    if not old or not new or old == new:
        return []
    pat = re.compile(_MEMBERS.format(re.escape(old)) + "|" + r"(## added via dynamic class ){}( ##)".format(re.escape(old))
                     + "|" + r"(^[ \t]*USE[ \t]+(?:ALLOW|DENY)[ \t]+){}([ \t]*$)".format(re.escape(old)), re.M)
    changed = []
    with transaction.atomic():
        for p in PoolTemplate.objects.all():
            txt = pat.sub(_r(new), p.template or "")
            if txt != p.template:
                p.template = txt
                p.save()
                changed.append(f"pool {p.name}")
        for o in SubnetOverride.objects.select_related("pool"):
            txt = pat.sub(_r(new), o.code or "")
            if txt != o.code:
                o.code = txt
                o.save()
                changed.append(f"subnet {o.prefix_text}")
        for b in BaseConfig.objects.all():
            txt = pat.sub(_r(new), b.static_text or "")
            if txt != b.static_text:
                b.static_text = txt
                b.save()
                changed.append("dhcpd.conf")
    return changed


def sync_name(hg, name: str) -> list:
    """The group object got a new name: rename the class everywhere, then store the new name."""
    old = hg.name
    if old == name:
        return []
    with transaction.atomic():
        changed = rename_class(old, name) if old else []
        hg.name = name
        hg.save(update_fields=["name"])
    return changed


# ---- NetBox group object: rename = class rename everywhere, delete refused while the class is used ----
def _hg_for(sender, instance):
    from .models import HostConfig, HostGroup

    if sender._meta.app_label == "netbox_isc_dhcp" or not instance.pk:
        return None, None
    cfg = HostConfig.objects.first()
    label = f"{sender._meta.app_label}.{sender._meta.model_name}"
    if cfg is None or cfg.group_model != label:
        return None, None
    return cfg, HostGroup.objects.filter(group_model=label, group_pk=instance.pk).first()


def group_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    try:
        cfg, hg = _hg_for(sender, instance)
    except Exception:
        return
    if hg is None:
        return
    from .logic import field_options, name_of

    gkeys = {o["key"] for o in field_options(sender)}
    name = name_of(instance, cfg.group_name_field if cfg.group_name_field in gkeys else "")[:200]
    if name != hg.name:
        sync_name(hg, name)


def group_deleting(sender, instance, **kwargs):
    cfg, hg = _hg_for(sender, instance)
    if hg is None:
        return
    from ..export.models import ExportFile
    from ..services import dynamic_classes
    from .usage import defined_classes

    mine, others = set(), set()
    for key, content in ExportFile.objects.filter(area="table").values_list("key", "content"):
        (mine if key.startswith(f"group:{hg.pk}:") else others).update(defined_classes(content))
    now = dynamic_classes()
    lost = {c: u for c, u in used_classes().items() if c in mine and c in now and c not in others | _static_classes()}
    if lost:
        from utilities.exceptions import AbortRequest

        raise AbortRequest(refuse_text(lost))


def connect():
    from django.db.models.signals import post_save, pre_delete

    post_save.connect(group_saved, dispatch_uid="isc_dhcp_class_rename")
    pre_delete.connect(group_deleting, dispatch_uid="isc_dhcp_class_protect")
