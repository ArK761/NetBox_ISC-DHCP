from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from ..i18n import t, tmsg
from ..source_fields import distinct_values, field_options, get_model, source_label, source_models
from .logic import MAX_MAC_FIELDS, overview
from .models import host_config


class HostsView(LoginRequiredMixin, View):
    def get(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.view_hostconfig"):
            raise PermissionDenied
        cfg = host_config()
        groups = {}
        for value, app, label in source_models():
            groups.setdefault(app, []).append((value, label))
        edit = request.GET.get("edit", "")
        ov = overview(cfg, int(edit) if edit.isdigit() else None)
        for r in ov["rows"] or []:
            r["warnings"] = [tmsg(w) for w in r["warnings"]]
            r["hosts_text"] = t("hosts.static_hosts", n=r["hosts"])
        order = {k: i for i, k in enumerate(cfg.mac_fields or [], 1)}
        mac_opts = [dict(o, order=order.get(o["key"], 0)) for o in field_options(ov["mac_model"])]
        labels = {o["key"]: o["label"] for o in mac_opts}
        selected = sum(1 for g in ov["groups"] if g["selected"])
        need = {"group_model": "hosts.need_group_model", "groups": "hosts.need_groups", "mac_model": "hosts.need_mac_model",
                "link": "hosts.need_link", "mac": "hosts.need_mac"}
        return render(request, "netbox_isc_dhcp/hosts/hosts.html", {
            "cfg": cfg, "ov": ov, "source_groups": groups,
            "group_label": source_label(cfg.group_model), "mac_label": source_label(cfg.mac_model),
            "group_fields": field_options(ov["group_model"]), "mac_opts": mac_opts,
            "ip_label": labels.get(cfg.ip_field, ""), "host_name_label": labels.get(cfg.host_name_field, ""),
            "group_name_label": {o["key"]: o["label"] for o in field_options(ov["group_model"])}.get(cfg.group_name_field, ""),
            "mac_sel": sorted([o for o in mac_opts if o["order"]], key=lambda o: o["order"]), "link_label": dict(ov["links"]).get(ov["link"], ""),
            "groups_count_text": t("hosts.groups_selected", n=selected, total=len(ov["groups"])),
            "used_fields": [c["field"] for c in ov["conditions"]],
            "mac_fields_title": t("hosts.mac_fields", n=MAX_MAC_FIELDS),
            "need_texts": [t(need[n]) for n in ov["need"]],
        })


class HostsInlineView(LoginRequiredMixin, View):
    """Click-to-edit values of the hosts page; returns to the card that was changed."""

    def post(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.change_hostconfig"):
            raise PermissionDenied
        cfg = host_config()
        field, value = request.POST.get("field"), request.POST.get("value", "").strip()
        valid_models = {v for v, _, _ in source_models()}
        group_keys = {o["key"] for o in field_options(get_model(cfg.group_model))}
        mac_keys = {o["key"] for o in field_options(get_model(cfg.mac_model))}
        err, anchor, edit = "", "isc-src-mac", None
        if field in ("group_model", "mac_model"):
            if value and value not in valid_models:
                err = t("hosts.err_object")
            elif value != getattr(cfg, field):
                setattr(cfg, field, value)
                cfg.link_field = ""
                if field == "group_model":  # names / chosen groups belong to the old object type
                    cfg.group_name_field, cfg.group_conditions, anchor = "name", [], "isc-src-group"
                else:
                    cfg.mac_fields, cfg.ip_field, cfg.host_name_field = [], "", "name"
        elif field == "group_name_field":
            anchor = "isc-src-group"
            if value not in group_keys:
                err = t("hosts.err_field")
            else:
                cfg.group_name_field = value
        elif field and field.startswith("cond_"):
            anchor = "isc-groups"
            conds = list(cfg.group_conditions or [])
            i = request.POST.get("row", "")
            row = conds[int(i)] if i.isdigit() and int(i) < len(conds) else None
            model = get_model(cfg.group_model)
            if field == "cond_add" and value in group_keys:
                conds.append({"field": value, "values": [], "mode": "include"})
            elif row is not None and field == "cond_mode" and value in ("include", "exclude"):
                row["mode"] = value
            elif row is not None and field == "cond_set":  # mode + ticked values saved together
                allowed = {v for v, _ in distinct_values(model, row["field"])}
                row["values"] = [v for v in request.POST.getlist("values") if v in allowed]
                if request.POST.get("mode") in ("include", "exclude"):
                    row["mode"] = request.POST["mode"]
            elif row is not None and field == "cond_all":
                row["values"] = [v for v, _ in distinct_values(model, row["field"])]
            elif row is not None and field == "cond_none":
                row["values"] = []
            elif row is not None and field == "cond_del":
                conds.pop(int(i))
            cfg.group_conditions = conds
            if field == "cond_add":
                edit = len(conds) - 1
            elif field in ("cond_all", "cond_none") and row is not None:
                edit = int(i)
        elif field == "host_name_field":
            if value not in mac_keys:
                err = t("hosts.err_field")
            else:
                cfg.host_name_field = value
        elif field == "link_field":
            cfg.link_field = value
        elif field == "mac_fields":
            keys = [k for k in request.POST.getlist("value") if k]
            if len(keys) > MAX_MAC_FIELDS:
                err = t("hosts.err_max_macs", n=MAX_MAC_FIELDS)
            elif any(k not in mac_keys for k in keys):
                err = t("hosts.err_field")
            else:  # keep the order in which the fields were ticked
                old = [k for k in cfg.mac_fields or [] if k in keys]
                cfg.mac_fields = old + [k for k in keys if k not in old]
        elif field == "ip_field":
            if value and value not in mac_keys:
                err = t("hosts.err_field")
            else:
                cfg.ip_field = value
        if err:
            messages.error(request, err)
        else:
            cfg.save()
        url = reverse("plugins:netbox_isc_dhcp:hosts")
        if edit is not None:
            return redirect(f"{url}?edit={edit}#c{edit}")
        return redirect(url + "#" + anchor)
