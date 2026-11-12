from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views import View

from ..i18n import t, tmsg
from ..source_fields import field_options, get_model, source_label, source_models
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
        ov = overview(cfg)
        for r in ov["rows"] or []:
            r["warnings"] = [tmsg(w) for w in r["warnings"]]
            r["hosts_text"] = t("hosts.static_hosts", n=r["hosts"])
        mac_opts = field_options(ov["mac_model"])
        labels = {o["key"]: o["label"] for o in mac_opts}
        return render(request, "netbox_isc_dhcp/hosts/hosts.html", {
            "cfg": cfg, "ov": ov, "source_groups": groups,
            "group_label": source_label(cfg.group_model), "mac_label": source_label(cfg.mac_model),
            "group_fields": field_options(ov["group_model"]), "mac_opts": mac_opts,
            "mac_labels": [labels.get(k, k) for k in cfg.mac_fields or []],
            "ip_label": labels.get(cfg.ip_field, ""), "link_label": dict(ov["links"]).get(ov["link"], ""),
            "group_count_text": t("hosts.n_objects", n=len(ov["groups"])),
            "mac_fields_title": t("hosts.mac_fields", n=MAX_MAC_FIELDS),
        })


class HostsInlineView(LoginRequiredMixin, View):
    """Click-to-edit values of the hosts page."""

    def post(self, request):
        if not request.user.has_perm("netbox_isc_dhcp.change_hostconfig"):
            raise PermissionDenied
        cfg = host_config()
        field, value = request.POST.get("field"), request.POST.get("value", "").strip()
        valid_models = {v for v, _, _ in source_models()}
        mac_keys = {o["key"] for o in field_options(get_model(cfg.mac_model))}
        err = ""
        if field in ("group_model", "mac_model"):
            if value and value not in valid_models:
                err = t("hosts.err_object")
            elif value != getattr(cfg, field):
                setattr(cfg, field, value)
                cfg.link_field = ""
                if field == "mac_model":  # fields belong to the old object type
                    cfg.mac_fields, cfg.ip_field = [], ""
        elif field == "link_field":
            cfg.link_field = value
        elif field == "mac_fields":
            keys = [k for k in request.POST.getlist("value") if k]
            if len(keys) > MAX_MAC_FIELDS:
                err = t("hosts.err_max_macs", n=MAX_MAC_FIELDS)
            elif any(k not in mac_keys for k in keys):
                err = t("hosts.err_field")
            else:
                cfg.mac_fields = list(dict.fromkeys(keys))
        elif field == "ip_field":
            if value and value not in mac_keys:
                err = t("hosts.err_field")
            else:
                cfg.ip_field = value
        if err:
            messages.error(request, err)
        else:
            cfg.save()
            messages.success(request, t("msg.saved"))
        return redirect("plugins:netbox_isc_dhcp:hosts")
