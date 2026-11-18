"""Agent on a DHCP server: state of every server, gates (ISC version, failed set, staged rollout) and the plan of steps."""
from django.utils import timezone

from .models import ExportFile

INTERVALS = (10, 30, 60, 300, 600, 1200, 1800)  # seconds, chosen in CFG pluginu -> DHCP servery
FAILED = ("test_failed", "rolled_back", "failed")


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


def enabled_servers():
    from .models import DHCPServer

    return list(DHCPServer.objects.filter(enabled=True).order_by("order", "pk"))


def first_server():
    lst = enabled_servers()
    return lst[0] if lst else None


def isc_versions() -> dict:
    """{version: [server names]} of enabled servers whose agent reported an installed ISC dhcpd."""
    out = {}
    for s in enabled_servers():
        if s.isc_version and s.isc_version != "none":
            out.setdefault(s.isc_version, []).append(s.name)
    return out


def isc_mismatch() -> bool:
    return len(isc_versions()) > 1


def running_mismatch() -> bool:
    """Enabled servers (that reported) run different CFG sets."""
    run = {s.running_hash for s in enabled_servers() if s.last_seen and s.running_hash}
    return len(run) > 1


def gate(server, manifest_hash):
    """(reason, [server names]) why this server must wait now, or ("", [])."""
    from ..models import settings_obj

    if server is None:
        return "", []
    if server.isc_version == "none":
        return "isc_missing", []
    first = first_server()
    if isc_mismatch() and (first is None or server.pk != first.pk):
        return "isc_mismatch", [first.name] if first else []
    if server.last_result in FAILED and server.last_hash == manifest_hash:
        return "failed_same", []  # never send the set that already failed here again (no endless restore loop)
    st = settings_obj()
    if (st and st.staged_rollout) or running_mismatch():
        before = [s for s in enabled_servers() if s.order < server.order]
        waiting = [s.name for s in before if not ((s.last_result == "ok" and s.last_hash == manifest_hash)
                                                  or s.released_hash == manifest_hash or s.isc_version == "none")]
        if waiting:
            return "staged", waiting
    return "", []


def waiting_for(server, manifest_hash):
    """Kept for callers: names of servers this one waits for (staged rollout / ISC mismatch)."""
    reason, names = gate(server, manifest_hash)
    return names if reason in ("staged", "isc_mismatch") else []


def managed_dirs():
    """Directories the agent may delete files in: current ones + every one used before (only below the base path)."""
    from ..models import base_path, settings_obj

    st = settings_obj()
    base = base_path()
    now = {p.rsplit("/", 1)[0] for p in ExportFile.objects.exclude(area="conf").values_list("path", flat=True)}
    old = set(st.agent_dirs or []) if st else set()
    return sorted(d for d in now | old if base and (d == base or d.startswith(base + "/")))


def make_plan(have: dict, server, file_url, report_url, manifest_hash, mode="plan"):
    """have = {path: sha256} on the server. plan = only changes (empty when nothing to do), export = everything."""
    from ..models import BACKUP_DIR, settings_obj

    if server is not None and server.last_result != "ok":
        mode = "export"  # never reported OK (or the last set failed) -> full set until the first OK
    rows = list(ExportFile.objects.order_by("area", "path").values("path", "area", "sha256", "size"))
    want = {r["path"]: r for r in rows}
    dirs = managed_dirs()
    download = list(rows) if mode == "export" else [r for r in rows if have.get(r["path"]) != r["sha256"]]
    delete = sorted(p for p in have if p not in want and p.rsplit("/", 1)[0] in dirs)  # only inside the managed dirs
    if not download and not delete:
        return []
    conf = next((r["path"] for r in rows if r["area"] == "conf"), "")
    st = settings_obj()
    backup = (st.agent_backup_dir if st and st.agent_backup_dir else BACKUP_DIR)
    cur = sorted({r["path"].rsplit("/", 1)[0] for r in rows if r["area"] != "conf"})
    steps = [{"op": "backup", "paths": ([conf] if conf else []) + cur, "to": backup}]
    # included files first, dhcpd.conf last: dhcpd.conf never points to a file that is not there yet
    for r in sorted(download, key=lambda r: r["area"] == "conf"):
        steps.append({"op": "download", "path": r["path"], "sha256": r["sha256"], "size": r["size"], "url": file_url(r["path"])})
    test = (st.agent_test_cmd if st else "dhcpd -t -cf {conf}").replace("{conf}", conf)
    steps.append({"op": "test", "cmd": test, "on_fail": "restore"})
    steps.append({"op": "restart", "cmd": st.agent_restart_cmd if st else "systemctl restart isc-dhcp-server", "on_fail": "restore"})
    for p in delete:
        steps.append({"op": "delete", "path": p})
    steps.append({"op": "report", "url": report_url, "hash": manifest_hash})
    for i, s in enumerate(steps, 1):
        s["step"] = i
    return steps


def as_text(info: dict, steps: list) -> str:
    """Plan for a bash agent: one line per item, fields separated by TAB (no JSON parser needed)."""
    lines = []
    for k, v in info.items():
        if isinstance(v, (list, tuple)):
            lines += [f"{k}\t{x}" for x in v]
        elif v not in (None, ""):
            lines.append(f"{k}\t{v}")
    for s in steps:
        op = s["op"]
        if op == "backup":
            lines.append("\t".join(["backup", s["to"]] + s["paths"]))
        elif op == "download":
            lines.append("\t".join(["download", s["path"], s["sha256"], s["url"]]))
        elif op in ("test", "restart"):
            lines.append(f"{op}\t{s['cmd']}")
        elif op == "delete":
            lines.append(f"delete\t{s['path']}")
        elif op == "report":
            lines.append(f"report\t{s['url']}")
    return "\n".join(lines) + "\n"


def parse_have(text: str) -> dict:
    """`sha256sum` output (sha  path per line) -> {path: sha}."""
    out = {}
    for line in (text or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1].lstrip("*").strip()] = parts[0].lower()
    return out


def heartbeat(server, request, data):
    """Store what the agent says about itself; audit only what changed."""
    from . import audit
    from .models import AuditEvent

    if server is None:
        return
    new = {
        "agent_version": str(data.get("agent", ""))[:50],
        "isc_version": str(data.get("isc", ""))[:100],
        "running_hash": str(data.get("running", ""))[:64],
    }
    run = data.get("dhcpd")
    new_running = None if run in (None, "") else str(run) in ("1", "true", "yes")
    changes = []
    for k, v in new.items():
        if v and v != getattr(server, k):
            changes.append({"path": k, "action": "update", "old": getattr(server, k), "new": v})
            setattr(server, k, v)
    if new_running is not None and new_running != server.dhcpd_running:
        changes.append({"path": "dhcpd_running", "action": "update", "old": str(server.dhcpd_running), "new": str(new_running)})
        server.dhcpd_running = new_running
    first_contact = server.last_seen is None
    server.last_seen = timezone.now()
    server.save(update_fields=["agent_version", "isc_version", "running_hash", "dhcpd_running", "last_seen"])
    if changes or first_contact:
        from ..i18n import t

        AuditEvent.objects.create(time=server.last_seen, kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                  manifest_hash=new["running_hash"], cause=t("aud.agent_first") if first_contact else t("aud.agent_state"),
                                  changes=changes)


def stale(server, interval) -> bool:
    """No contact for more than 3 intervals (or never)."""
    if server.last_seen is None:
        return True
    return (timezone.now() - server.last_seen).total_seconds() > 3 * max(interval, 10) + 30
