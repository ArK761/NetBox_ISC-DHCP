from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from ..i18n import t, tmsg
from ..models import DHCPPath, PluginSettings, settings_obj
from ..source_fields import distinct_values, field_options, get_model, source_label, source_models
from ..views import _editor_vars
from .codegen import DEFAULT_DYNAMIC, DEFAULT_STATIC, code_errors, render_files
from .logic import MAX_HOSTS, build_group, groups_overview, source_info
from .models import HostGroup, HostSource, host_config


def _source_groups():
    groups = {}
    for value, app, label in source_models():
        groups.setdefault(app, []).append((value, label))
    return groups


def _need_texts(need):
    keys = {"model": "hosts.need_model", "cond": "hosts.need_cond", "mac": "hosts.need_mac", "ip": "hosts.need_ip"}
    return [t(keys[n]) for n in need]


def _codes(request, cfg):
    drafts = request.session.get("hosts_code_draft", {})
    return [{"kind": k, "title": t("hosts.code_" + k), "default": cfg.is_default(k), "draft": k in drafts,
             "text": drafts.get(k, cfg.code(k)), "vars": t("hosts.code_vars_" + k)} for k in ("dynamic", "static")]


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
            "codes": _codes(request, cfg), "editor_vars": _editor_vars(),
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
        elif field in ("code_dynamic", "code_static", "code_reset_dynamic", "code_reset_static"):
            kind = field.rsplit("_", 1)[1]
            anchor = "isc-code-" + kind
            drafts = dict(request.session.get("hosts_code_draft", {}))
            code = "" if field.startswith("code_reset") else request.POST.get("value", "").replace("\r\n", "\n")
            default = DEFAULT_DYNAMIC if kind == "dynamic" else DEFAULT_STATIC
            if code.strip() == default.strip():
                code = ""
            bad = code_errors(code) if code else ""
            if bad:
                drafts[kind] = code
                err = t("hosts.code_err", err=tmsg(bad))
            else:
                drafts.pop(kind, None)
                setattr(cfg, kind + "_code", code)
                messages.success(request, t("hosts.code_saved"))
            request.session["hosts_code_draft"] = drafts
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


LOST_REASONS = ("no_mac", "no_ip", "bad_mac", "bad_ip", "bad_name", "dup_name")


class HostGroupView(LoginRequiredMixin, View):
    """One group: its sources (object, conditions, host rows MAC + IP) and the two files they make."""

    def get(self, request, pk):
        if not request.user.has_perm("netbox_isc_dhcp.view_hostconfig"):
            raise PermissionDenied
        hg = get_object_or_404(HostGroup, pk=pk)
        gm = get_model(hg.group_model)
        group_obj = gm.objects.filter(pk=hg.group_pk).first() if gm else None
        open_src, edit = request.GET.get("src", ""), request.GET.get("edit", "")
        built = build_group(hg)
        st = settings_obj()
        sources = []
        for src in hg.sources.all():
            info = source_info(src, int(edit) if edit.isdigit() and open_src == str(src.pk) else None)
            opts = field_options(info["model"])
            labels = {o["key"]: o["label"] for o in opts}
            rows = []
            for i, r in enumerate(src.hosts or [], 1):
                ok = r.get("mac") in labels and (not r.get("ip") or r["ip"] in labels)
                target = "static_dyn" if r.get("ip") and r.get("dyn") else "static" if r.get("ip") else "dynamic"
                rows.append({"index": i - 1, "n": i, "mac": labels.get(r.get("mac"), r.get("mac")), "ip": labels.get(r.get("ip"), r.get("ip")) if r.get("ip") else "",
                             "dyn": bool(r.get("dyn")), "ok": ok, "target": target, "target_text": t("hosts.to_" + target),
                             "hn": r.get("hn") or "name", "hn_text": {"name": t("hosts.hn_name"), "host": t("hosts.hn_host"), "none": t("hosts.hn_none")}.get(r.get("hn") or "name", labels.get(r.get("hn"), r.get("hn")))})
            used = {r.get("mac") for r in src.hosts or []} | {r.get("ip") for r in src.hosts or [] if r.get("ip")}
            info.update({"label": source_label(src.model), "opts": opts, "free": [o for o in opts if o["key"] not in used],
                         "mac_opts": [(o["key"], o["label"] + (f" ({t('hosts.used_row', n=n)})" if n else "")) for o in opts
                                      for n in [next((i for i, r in enumerate(src.hosts or [], 1) if r.get("mac") == o["key"]), 0)]
                                      if o["key"] not in {r.get("ip") for r in src.hosts or []}],
                         "need_texts": _need_texts(info["need"]), "hn_choices": [("name", t("hosts.hn_name")), ("host", t("hosts.hn_host")), ("none", t("hosts.hn_none"))], "rows": rows, "can_add": len(src.hosts or []) < MAX_HOSTS,
                         "host_name_label": labels.get(src.host_name_field, ""), "used_fields": [c["field"] for c in info["conditions"]],
                         "names_hint": t("hosts.names_hint1") if len(rows) <= 1 else t("hosts.names_hintn", n=len(rows))})
            sources.append(info)
        cfg = host_config()
        rendered = render_files(hg, built, {k: cfg.code(k) for k in ("dynamic", "static")})
        files = []
        for kind in ("dynamic", "static"):
            b = built[kind]
            rows = [(r[0], r[1], r[2] if kind == "static" else "") for r in b["rows"]]
            files.append({"kind": kind, "name": hg.file_name(kind), "suffix": hg.dynamic_suffix if kind == "dynamic" else hg.static_suffix,
                          "rows": rows[:500], "count": len(rows), "more": max(0, len(rows) - 500),
                          "count_text": t("hosts.hosts_count", n=len(rows)), "cfg_text": rendered[kind][0],
                          "cfg_error": tmsg(rendered[kind][1]) if rendered[kind][1] else "", "lines": rendered[kind][0].count("\n")})
        lc = built["lost_counts"]
        lost_parts = [f"{lc[k]}× {t('hosts.lost_' + k)}" for k in LOST_REASONS if lc.get(k)]
        others = [g for g in HostGroup.objects.filter(group_model=hg.group_model).exclude(pk=hg.pk) if g.sources.exists()]
        return render(request, "netbox_isc_dhcp/hosts/group.html", {
            "hg": hg, "group_obj": group_obj, "files": files, "sources": sources, "source_groups": _source_groups(),
            "warnings": [tmsg(w) for w in built["warnings"]], "others": others, "objects": built["objects"],
            "lost": [(h, t("hosts.lost_" + r), v) for h, r, v in built["lost"]],
            "lost_title": t("hosts.lost_title", n=len(built["lost"])), "lost_parts": " · ".join(lost_parts),
            "warn_title": t("hosts.warn_title", n=len(built["warnings"])),
            "table_dir": st.table_dir if st else None, "rows_title": t("hosts.rows_title", n=MAX_HOSTS),
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
            if value not in models_ok:
                err = t("hosts.err_object")
            else:
                last = hg.sources.order_by("-order").first()
                src = HostSource.objects.create(group=hg, model=value, order=(last.order if last else 0) + 10)
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
                    src.model, src.conditions, src.hosts, src.host_name_field = value, [], [], "name"
            elif field == "host_name_field":
                if value not in keys:
                    err = t("hosts.err_field")
                else:
                    src.host_name_field = value
            elif field == "row_add":
                rows = list(src.hosts or [])
                mac, ip = request.POST.get("mac", ""), request.POST.get("ip", "")
                labels = {o["key"]: o["label"] for o in field_options(get_model(src.model))}
                same = next((n for n, r in enumerate(rows, 1) if r.get("mac") == mac), None)
                if len(rows) >= MAX_HOSTS:
                    err = t("hosts.err_max_rows", n=MAX_HOSTS)
                elif mac not in keys or (ip and ip not in keys) or mac == ip:
                    err = t("hosts.err_field")
                elif same is not None and (bool(ip) == bool(rows[same - 1].get("ip")) or rows[same - 1].get("dyn")
                                           or (ip and request.POST.get("dyn") == "1")):
                    # the same MAC field may appear twice only as one static row (without class) + one dynamic row
                    r = rows[same - 1]
                    kind = "dyn_used" if not r.get("ip") else "both_used" if r.get("dyn") else "static_used"
                    err = t("hosts.err_" + kind, field=labels.get(mac, mac), n=same)
                elif ip and ip in {r.get("ip") for r in rows} | {r.get("mac") for r in rows if r.get("mac") != mac}:
                    err = t("hosts.err_used")
                else:
                    rows.append({"mac": mac, "ip": ip, "dyn": bool(ip) and request.POST.get("dyn") == "1"})
                    src.hosts = rows
            elif field == "row_hn":
                rows = list(src.hosts or [])
                i = request.POST.get("row", "")
                if not (i.isdigit() and int(i) < len(rows)) or (value not in ("name", "host", "none") and value not in keys):
                    err = t("hosts.err_field")
                else:
                    rows[int(i)] = dict(rows[int(i)], hn=value)
                    src.hosts = rows
            elif field in ("row_del", "row_dyn"):
                rows = list(src.hosts or [])
                i = request.POST.get("row", "")
                if i.isdigit() and int(i) < len(rows):
                    if field == "row_del":
                        rows.pop(int(i))
                    elif rows[int(i)].get("ip"):
                        r = rows[int(i)]
                        solo = next((n for n, x in enumerate(rows, 1) if x is not r and x.get("mac") == r["mac"] and not x.get("ip")), None)
                        if not r.get("dyn") and solo:  # its MAC already goes to Dynamic by its own row
                            labels = {o["key"]: o["label"] for o in field_options(get_model(src.model))}
                            err = t("hosts.err_dyn_used", field=labels.get(r["mac"], r["mac"]), n=solo)
                        else:
                            rows[int(i)] = dict(r, dyn=not r.get("dyn"))
                    src.hosts = rows
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
