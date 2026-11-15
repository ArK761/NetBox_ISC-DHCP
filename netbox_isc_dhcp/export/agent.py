"""Plan for the agent on a DHCP server: exact steps from what it has (path -> sha256) to the current set."""
from .models import ExportFile


def server_for(request):
    """DHCPServer of the client IP (or ?server=<pk> for a logged-in admin)."""
    from .audit import client_ip
    from .models import DHCPServer
    from .servers import resolve

    pk = request.GET.get("server", "")
    if request.user.is_authenticated and pk.isdigit():
        return DHCPServer.objects.filter(pk=int(pk)).first()
    ip = client_ip(request)
    for s in DHCPServer.objects.filter(enabled=True):
        if ip in resolve(s.address)[0]:
            return s
    return None


def make_plan(have: dict, server, file_url, report_url, manifest_hash, mode="plan"):
    """have = {path: sha256} on the server. plan = only changes (empty when nothing to do), export = everything."""
    from ..models import base_path

    rows = list(ExportFile.objects.order_by("area", "path").values("path", "area", "sha256", "size"))
    want = {r["path"]: r for r in rows}
    dirs = sorted({r["path"].rsplit("/", 1)[0] for r in rows if r["area"] != "conf"})
    download = list(rows) if mode == "export" else [r for r in rows if have.get(r["path"]) != r["sha256"]]
    delete = sorted(p for p in have if p not in want and p.rsplit("/", 1)[0] in dirs)  # only inside the managed dirs
    if not download and not delete:
        return []
    conf = next((r["path"] for r in rows if r["area"] == "conf"), "")
    backup = (server.backup_dir if server and server.backup_dir else f"{base_path() or ''}/bck")
    steps = [{"op": "backup", "paths": ([conf] if conf else []) + dirs, "to": backup}]
    # included files first, dhcpd.conf last: dhcpd.conf never points to a file that is not there yet
    for r in sorted(download, key=lambda r: r["area"] == "conf"):
        steps.append({"op": "download", "path": r["path"], "sha256": r["sha256"], "size": r["size"], "url": file_url(r["path"])})
    test = (server.test_cmd if server else "dhcpd -t -cf {conf}").replace("{conf}", conf)
    steps.append({"op": "test", "cmd": test, "on_fail": "restore"})
    steps.append({"op": "restart", "cmd": server.restart_cmd if server else "systemctl restart isc-dhcp-server", "on_fail": "restore"})
    for p in delete:
        steps.append({"op": "delete", "path": p})
    steps.append({"op": "report", "url": report_url, "hash": manifest_hash})
    for i, s in enumerate(steps, 1):
        s["step"] = i
    return steps


def waiting_for(server, manifest_hash):
    """Staged rollout: the enabled servers before this one (by order) that have not reported OK for this hash."""
    from ..models import settings_obj
    from .models import DHCPServer

    st = settings_obj()
    if not (st and st.staged_rollout) or server is None:
        return []
    before = DHCPServer.objects.filter(enabled=True, order__lt=server.order)
    return [s.name for s in before if not (s.last_result == "ok" and s.last_hash == manifest_hash)]
