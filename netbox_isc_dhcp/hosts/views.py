from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from ..i18n import t, tmsg
from ..models import DHCPPath, PluginSettings, settings_obj
from ..source_fields import distinct_values, field_options, get_model, source_label, source_models
from .logic import MAX_MAC_FIELDS, build_group, groups_overview, source_info
from .models import HostGroup, HostSource, host_config


def _source_groups():
    groups = {}
    for value, app, label in source_models():
        groups.setdefault(app, []).append((value, label))
    return groups


def _need_texts(need):
    keys = {"model": "hosts.need_model", "cond": "hosts.need_cond", "mac": "hosts.need_mac", "ip": "hosts.need_ip"}
    return [t(keys[n]) for n in need]


class HostsView(LoginRequiredMixin, View):
    """Table source (groups), table directory and the list of groups (like the pools list)."""

    def get(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.view_hostconfig"):
            raise PermissionDenied
        cfg = host_config()
        edit = request.GET.get("edit", "")
        ov = groups_overview(cfg, int(edit) if edit.isdigit() else None)
        for r in ov["groups"]:
            r["warnings"] = [tmsg(w) for w in r["warnings"]]
        gfields = field_options(ov["group_model"])
        st = settings_obj()
        return render(request, "netbox_isc_dhcp/hosts/hosts.html", {
            "cfg": cfg, "ov": ov, "source_groups": _source_groups(), "group_label": source_label(cfg.group_model),
            "group_fields": gfields, "group_name_label": {o["key"]: o["label"] for o in gfields}.get(cfg.group_name_field, ""),
            "used_fields": [c["field"] for c in ov["conditions"]],
            "groups_count_text": t("hosts.groups_selected", n=len(ov["groups"]), total=ov.get("total", 0)),
            "table_dir": st.table_dir if st else None, "subdirs": DHCPPath.objects.all(),
        })


class HostsInlineView(LoginRequiredMixin, View):
    """Click-to-edit values of the hosts page; returns to the part that was changed."""

    def post(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.change_hostconfig"):
            raise PermissionDenied
        cfg = host_config()
        field, value = request.POST.get("field"), request.POST.get("value", "").strip()
        group_keys = {o["key"] for o in field_options(get_model(cfg.group_model))}
        err, anchor, edit = "", "isc-src-group", None
        if field == "group_model":
            if value and value not in {v for v, _, _ in source_models()}:
                err = t("hosts.err_object")
            elif value != cfg.group_model:
                cfg.group_model, cfg.group_name_field, cfg.group_conditions = value, "name", []
        elif field == "group_name_field":
            if value not in group_keys:
                err = t("hosts.err_field")
            else:
                cfg.group_name_field = value
        elif field == "table_dir":
            st = settings_obj() or PluginSettings.objects.create()
            st.table_dir_id = int(value) if value.isdigit() and DHCPPath.objects.filter(pk=int(value)).exists() else None
            st.save()
        elif field and field.startswith("cond_"):
            anchor = "isc-conds"
            conds = list(cfg.group_conditions or [])
            i = request.POST.get("row", "")
            row = conds[int(i)] if i.isdigit() and int(i) < len(conds) else None
            model = get_model(cfg.group_model)
            if field == "cond_add" and value in group_keys:
                conds.append({"field": value, "values": [], "mode": "include"})
                edit = len(conds) - 1
            elif row is not None and field == "cond_set":  # mode + ticked values saved together
                allowed = {v for v, _ in distinct_values(model, row["field"])}
                row["values"] = [v for v in request.POST.getlist("values") if v in allowed]
                if request.POST.get("mode") in ("include", "exclude"):
                    row["mode"] = request.POST["mode"]
            elif row is not None and field in ("cond_all", "cond_none"):
                row["values"] = [v for v, _ in distinct_values(model, row["field"])] if field == "cond_all" else []
                edit = int(i)
            elif row is not None and field == "cond_del":
                conds.pop(int(i))
            cfg.group_conditions = conds
        if err:
            messages.error(request, err)
        else:
            cfg.save()
        url = reverse("plugins:netbox_isc_dhcp:hosts")
        return redirect(f"{url}?edit={edit}#c{edit}" if edit is not None else f"{url}#{anchor}")


class HostGroupView(LoginRequiredMixin, View):
    """One group: its two files, each built from its own sources (object, conditions, MAC, IP)."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.view_hostconfig"):
            raise PermissionDenied
        hg = get_object_or_404(HostGroup, pk=pk)
        gm = get_model(hg.group_model)
        group_obj = gm.objects.filter(pk=hg.group_pk).first() if gm else None
        open_src, edit = request.GET.get("src", ""), request.GET.get("edit", "")
        built = build_group(hg)
        st = settings_obj()
        files = []
        for kind in ("dynamic", "static"):
            sources = []
            for src in hg.sources.filter(kind=kind):
                info = source_info(src, int(edit) if edit.isdigit() and open_src == str(src.pk) else None)
                order = {k: i for i, k in enumerate(src.mac_fields or [], 1)}
                opts = [dict(o, order=order.get(o["key"], 0)) for o in field_options(info["model"])]
                labels = {o["key"]: o["label"] for o in opts}
                info.update({"label": source_label(src.model), "opts": opts, "need_texts": _need_texts(info["need"]),
                             "mac_sel": sorted([o for o in opts if o["order"]], key=lambda o: o["order"]),
                             "host_name_label": labels.get(src.host_name_field, ""), "ip_label": labels.get(src.ip_field, ""),
                             "used_fields": [c["field"] for c in info["conditions"]]})
                sources.append(info)
            b = built[kind]
            rows = ([(h.name, m, "") for h in b["hosts"] for m in h.macs] if kind == "dynamic" else
                    [(h.name if len(h.macs) == 1 else f"{h.name}_{i}", m, h.ip) for h in b["hosts"] for i, m in enumerate(h.macs, 1)])
            files.append({"kind": kind, "name": hg.file_name(kind), "suffix": hg.dynamic_suffix if kind == "dynamic" else hg.static_suffix,
                          "sources": sources, "built": b, "rows": rows[:500], "more": max(0, len(rows) - 500)})
        others = [g for g in HostGroup.objects.filter(group_model=hg.group_model).exclude(pk=hg.pk) if g.sources.exists()]
        return render(request, "netbox_isc_dhcp/hosts/group.html", {
            "hg": hg, "group_obj": group_obj, "files": files, "source_groups": _source_groups(),
            "warnings": [tmsg(w) for w in built["warnings"]], "others": others,
            "table_dir": st.table_dir if st else None, "mac_fields_title": t("hosts.mac_fields", n=MAX_MAC_FIELDS),
        })


class HostGroupInlineView(LoginRequiredMixin, View):
    """Click-to-edit values of a group page: on/off, file suffixes, sources and their conditions / fields."""

    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_hostconfig"):
            raise PermissionDenied
        hg = get_object_or_404(HostGroup, pk=pk)
        field, value = request.POST.get("field", ""), request.POST.get("value", "").strip()
        sid = request.POST.get("src", "")
        src = hg.sources.filter(pk=int(sid)).first() if sid.isdigit() else None
        models_ok = {v for v, _, _ in source_models()}
        err, anchor, edit = "", "isc-files", None
        if field == "enabled":
            hg.enabled = value == "1"
        elif field in ("dynamic_suffix", "static_suffix"):
            import re
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,50}", value):
                err = t("hosts.err_suffix")
            else:
                setattr(hg, field, value)
        elif field == "src_add":
            kind = request.POST.get("kind")
            if kind not in ("dynamic", "static") or value not in models_ok:
                err = t("hosts.err_object")
            else:
                last = hg.sources.filter(kind=kind).order_by("-order").first()
                src = HostSource.objects.create(group=hg, kind=kind, model=value, order=(last.order if last else 0) + 10)
        elif field == "copy_from":
            other = HostGroup.objects.filter(pk=int(value) if value.isdigit() else 0, group_model=hg.group_model).first()
            if other is None:
                err = t("hosts.err_copy")
            else:
                hg.sources.all().delete()
                for o in other.sources.all():
                    HostSource.objects.create(group=hg, **o.copy_fields())
                hg.dynamic_suffix, hg.static_suffix = other.dynamic_suffix, other.static_suffix
                messages.success(request, t("hosts.copied", name=other.name))
        elif src is not None:
            keys = {o["key"] for o in field_options(get_model(src.model))}
            if field == "src_del":
                src.delete()
                src = None
            elif field == "src_model":
                if value not in models_ok:
                    err = t("hosts.err_object")
                elif value != src.model:  # fields belong to the old object type
                    src.model, src.conditions, src.mac_fields, src.ip_field, src.host_name_field = value, [], [], "", "name"
            elif field == "host_name_field":
                if value not in keys:
                    err = t("hosts.err_field")
                else:
                    src.host_name_field = value
            elif field == "ip_field":
                if value and value not in keys:
                    err = t("hosts.err_field")
                else:
                    src.ip_field = value
            elif field == "mac_fields":
                picked = [k for k in request.POST.getlist("value") if k]
                if len(picked) > MAX_MAC_FIELDS:
                    err = t("hosts.err_max_macs", n=MAX_MAC_FIELDS)
                elif any(k not in keys for k in picked):
                    err = t("hosts.err_field")
                else:  # keep the order in which the fields were ticked
                    old = [k for k in src.mac_fields or [] if k in picked]
                    src.mac_fields = old + [k for k in picked if k not in old]
            elif field.startswith("cond_"):
                model = get_model(src.model)
                conds = list(src.conditions or [])
                i = request.POST.get("row", "")
                row = conds[int(i)] if i.isdigit() and int(i) < len(conds) else None
                if field == "cond_add" and value in keys:
                    conds.append({"field": value, "values": [], "mode": "include"})
                    edit = len(conds) - 1
                elif row is not None and field == "cond_set":
                    allowed = {v for v, _ in distinct_values(model, row["field"])}
                    row["values"] = [v for v in request.POST.getlist("values") if v in allowed]
                    if request.POST.get("mode") in ("include", "exclude"):
                        row["mode"] = request.POST["mode"]
                elif row is not None and field in ("cond_all", "cond_none"):
                    row["values"] = [v for v, _ in distinct_values(model, row["field"])] if field == "cond_all" else []
                    edit = int(i)
                elif row is not None and field == "cond_del":
                    conds.pop(int(i))
                src.conditions = conds
            if src is not None and not err:
                src.save()
        if err:
            messages.error(request, err)
        else:
            hg.save()
        url = hg.get_absolute_url()
        if request.POST.get("next") == "list":
            return redirect(reverse("plugins:netbox_isc_dhcp:hosts") + f"#g{hg.pk}")
        if src is not None and edit is not None:
            return redirect(f"{url}?src={src.pk}&edit={edit}#s{src.pk}c{edit}")
        return redirect(f"{url}#s{src.pk}" if src is not None else f"{url}#{anchor}")
