from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from ..i18n import t, tmsg
from ..models import DHCPPath, PluginSettings, settings_obj
from ..source_fields import distinct_values, field_options, get_model, source_label, source_models
from .logic import MAX_MAC_FIELDS, group_hosts, groups_overview
from .models import HostGroup, host_config


def _source_groups():
    groups = {}
    for value, app, label in source_models():
        groups.setdefault(app, []).append((value, label))
    return groups


def _need_texts(need):
    keys = {"mac_model": "hosts.need_mac_model", "link": "hosts.need_link", "mac": "hosts.need_mac"}
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
            r["source_label"] = source_label(r["hg"].mac_model)
            r["need_texts"] = _need_texts(r["need"])
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
    """One group: where its hosts come from (object, fields) and which hosts go to which table."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.view_hostconfig"):
            raise PermissionDenied
        hg = get_object_or_404(HostGroup, pk=pk)
        gm = get_model(hg.group_model)
        group_obj = gm.objects.filter(pk=hg.group_pk).first() if gm else None
        info = group_hosts(hg, group_obj) if group_obj is not None else {"need": [], "links": [], "link": "", "warnings": []}
        order = {k: i for i, k in enumerate(hg.mac_fields or [], 1)}
        opts = [dict(o, order=order.get(o["key"], 0)) for o in field_options(get_model(hg.mac_model))]
        labels = {o["key"]: o["label"] for o in opts}
        st = settings_obj()
        others = [g for g in HostGroup.objects.filter(group_model=hg.group_model).exclude(pk=hg.pk) if g.mac_model]
        dyn_rows = [(t_.name, m) for t_ in info.get("dynamic", []) for m in t_.macs]
        static_rows = [(t_.name if len(t_.macs) == 1 else f"{t_.name}_{i}", m, t_.ip) for t_ in info.get("static", []) for i, m in enumerate(t_.macs, 1)]
        return render(request, "netbox_isc_dhcp/hosts/group.html", {
            "hg": hg, "group_obj": group_obj, "info": info, "source_groups": _source_groups(),
            "mac_label": source_label(hg.mac_model), "opts": opts, "mac_sel": sorted([o for o in opts if o["order"]], key=lambda o: o["order"]),
            "host_name_label": labels.get(hg.host_name_field, ""), "ip_label": labels.get(hg.ip_field, ""),
            "link_label": dict(info.get("links", [])).get(info.get("link", ""), ""),
            "need_texts": _need_texts(info.get("need", [])), "warnings": [tmsg(w) for w in info.get("warnings", [])],
            "others": others, "dyn_rows": dyn_rows[:500], "static_rows": static_rows[:500],
            "table_dir": st.table_dir if st else None,
            "mac_fields_title": t("hosts.mac_fields", n=MAX_MAC_FIELDS),
        })


class HostGroupInlineView(LoginRequiredMixin, View):
    def post(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.change_hostconfig"):
            raise PermissionDenied
        hg = get_object_or_404(HostGroup, pk=pk)
        field, value = request.POST.get("field"), request.POST.get("value", "").strip()
        keys = {o["key"] for o in field_options(get_model(hg.mac_model))}
        err = ""
        if field == "mac_model":
            if value and value not in {v for v, _, _ in source_models()}:
                err = t("hosts.err_object")
            elif value != hg.mac_model:  # fields belong to the old object type
                hg.mac_model, hg.link_field, hg.mac_fields, hg.ip_field, hg.host_name_field = value, "", [], "", "name"
        elif field == "link_field":
            hg.link_field = value
        elif field in ("host_name_field", "ip_field"):
            if (value or field == "host_name_field") and value not in keys:
                err = t("hosts.err_field")
            else:
                setattr(hg, field, value)
        elif field == "mac_fields":
            picked = [k for k in request.POST.getlist("value") if k]
            if len(picked) > MAX_MAC_FIELDS:
                err = t("hosts.err_max_macs", n=MAX_MAC_FIELDS)
            elif any(k not in keys for k in picked):
                err = t("hosts.err_field")
            else:  # keep the order in which the fields were ticked
                old = [k for k in hg.mac_fields or [] if k in picked]
                hg.mac_fields = old + [k for k in picked if k not in old]
        elif field == "copy_from":
            src = HostGroup.objects.filter(pk=int(value) if value.isdigit() else 0, group_model=hg.group_model).first()
            if src is None:
                err = t("hosts.err_copy")
            else:
                for k, v in src.source_fields().items():
                    setattr(hg, k, v)
                messages.success(request, t("hosts.copied", name=src.name))
        if err:
            messages.error(request, err)
        else:
            hg.save()
        return redirect(hg.get_absolute_url())
