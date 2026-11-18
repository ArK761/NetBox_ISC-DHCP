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
        before = [s for s in enabled_servers() if s.order < server.order and s.last_seen]  # no agent yet = blocks nobody
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


_WHY = (  # agent text (English) -> i18n key; the rest after ':' is kept (command / log line)
    ("crash/kill (no stop command), last dhcpd log:", "why.kill_log"),
    ("crash/kill (no stop command in the journal)", "why.kill_none"),
    ("crash/kill:", "why.kill"),
    ("CRASH:", "why.crash"),
    ("command (sudo):", "why.sudo"),
    ("command: systemctl/service stop (root)", "why.root_stop"),
    ("command: systemctl/service start (root)", "why.root_start"),
    ("dhcpd started directly (not through the service)", "why.direct"),
    ("no journal - cannot tell", "why.nojournal"),
)


def why_text(raw):
    """Translate the agent's reason why dhcpd stopped/started (plugin language)."""
    from ..i18n import t

    for prefix, key in _WHY:
        if raw.startswith(prefix):
            return t(key) + raw[len(prefix):]
    return raw


def heartbeat(server, request, data):
    """Store what the agent says about itself; audit what changed, in plain words."""
    from ..i18n import t
    from . import audit, versions
    from .models import AuditEvent

    if server is None:
        return
    agent = str(data.get("agent", ""))[:50]
    isc = str(data.get("isc", ""))[:100]
    running = str(data.get("running", ""))[:64]
    run = data.get("dhcpd")
    dhcpd = None if run in (None, "") else str(run) in ("1", "true", "yes")
    first = server.last_seen is None
    msgs, changes = [], []
    if first:
        msgs.append(t("aud.ag_first", v=agent or "?"))
    elif agent and agent != server.agent_version:
        msgs.append(t("aud.ag_updated", old=server.agent_version or "?", new=agent))
    if isc and isc != server.isc_version or (first and isc):
        if isc == "none":
            msgs.append(t("aud.ag_isc_none"))
        elif server.isc_version in ("", "none"):
            msgs.append(t("aud.ag_isc_new", v=isc))
        else:
            msgs.append(t("aud.ag_isc_changed", old=server.isc_version, new=isc))
    event = str(data.get("dhcpd_event", ""))[:20]  # agent_start | agent_stop | manual_start | manual_stop
    if isc != "none" and dhcpd is not None and (dhcpd != server.dhcpd_running or first or server.isc_version in ("", "none")):
        why = str(data.get("dhcpd_why", ""))[:300]
        if event in ("manual_start", "manual_stop", "agent_start", "agent_stop"):
            msgs.append(t("aud.ag_" + event) + (f" – {why_text(why)}" if why and event.startswith("manual") else ""))
        else:
            msgs.append(t("aud.ag_dhcpd_up") if dhcpd else t("aud.ag_dhcpd_down"))
        recent_admin = server.dhcpd_by == "admin" and server.dhcpd_since and (timezone.now() - server.dhcpd_since).total_seconds() < 600
        pending = server.agent_cmd.split(":", 1)[0] in ("start", "stop", "restart")
        server.dhcpd_since = timezone.now()
        server.dhcpd_why = why if event.startswith("manual") else ""
        if event.startswith("agent") and (pending or recent_admin):
            server.dhcpd_by = "admin"  # started / stopped by a button in NetBox
        else:
            server.dhcpd_by = "manual" if event.startswith("manual") else ("agent" if event.startswith("agent") else "")
    done = str(data.get("cmd_done", ""))[:200]  # <id>:<ok|failed>:<text>
    if done and server.agent_cmd and done.split(":", 1)[0] == server.agent_cmd.split(":", 1)[1]:
        _, res, *txt = done.split(":", 2) + [""]
        if res == "ok" and server.agent_cmd.split(":", 1)[0] in ("start", "stop", "restart"):
            if server.dhcpd_by != "admin":
                server.dhcpd_since = timezone.now()
            server.dhcpd_by = "admin"
        msgs.append(t("aud.cmd_done", cmd=t("srv.cmd_%s" % server.agent_cmd.split(":", 1)[0]), res=res, txt=(txt[0] if txt else "")[:150]))
        server.agent_cmd = ""
    if running and running != server.running_hash:
        msgs.append(t("aud.ag_runs", cfg=versions.label(running)))
    for k, v in (("agent_version", agent), ("isc_version", isc), ("running_hash", running)):
        if v and v != getattr(server, k):
            changes.append({"path": k, "action": "update", "old": getattr(server, k), "new": v})
            setattr(server, k, v)
    if dhcpd is not None and dhcpd != server.dhcpd_running:
        changes.append({"path": "dhcpd_running", "action": "update", "old": str(server.dhcpd_running), "new": str(dhcpd)})
        server.dhcpd_running = dhcpd
    server.last_seen = timezone.now()
    server.save(update_fields=["agent_version", "isc_version", "running_hash", "dhcpd_running", "last_seen", "dhcpd_since", "dhcpd_by", "dhcpd_why", "agent_cmd"])
    if not msgs:  # nothing changed: a status line at least once an hour
        from datetime import timedelta

        if not AuditEvent.objects.filter(kind="agent", server=server.name, time__gte=server.last_seen - timedelta(hours=1)).exclude(result="refused").exists():
            msgs.append(t("aud.ag_status", state=status_text(server)))
    if msgs:
        AuditEvent.objects.create(time=server.last_seen, kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                  manifest_hash=running, cause="; ".join(msgs), changes=changes)


def status_text(server):
    """agent 1.3.0 · ISC 4.4.3-P1 · dhcpd beží · CFG 18.11.26_003"""
    from ..i18n import t
    from . import versions

    parts = [f"agent {server.agent_version or '?'}"]
    parts.append(t("srv.isc_none") if server.isc_version == "none" else f"ISC {server.isc_version or '?'}")
    if server.isc_version not in ("", "none") and server.dhcpd_running is not None:
        parts.append(t("aud.ag_dhcpd_up") if server.dhcpd_running else t("aud.ag_dhcpd_down"))
    parts.append(f"CFG {versions.label(server.running_hash)}" if server.running_hash else t("aud.ag_no_cfg"))
    return " · ".join(parts)


def stale(server, interval) -> bool:
    """No contact for more than 3 intervals (or never)."""
    if server.last_seen is None:
        return True
    return (timezone.now() - server.last_seen).total_seconds() > 3 * max(interval, 10) + 30


def first_block(server):
    """Why this server cannot become First (i18n key) or "": agent online and ISC installed are required."""
    from ..models import settings_obj

    st = settings_obj()
    if not server.enabled:
        return "srv.fb_off"
    if server.last_seen is None:
        return "srv.never_seen"
    if stale(server, st.agent_interval if st else 60):
        return "srv.silent"
    if server.isc_version in ("", "none"):
        return "srv.isc_none"
    return ""


# ---- agent shipped with the plugin (NetBox knows the newest version and can push it) ----
GITHUB_AGENT = "https://raw.githubusercontent.com/ArK761/NetBox_ISC-DHCP/claude/skeleton-pool-planner/netbox_isc_dhcp/agent_dist/isc-dhcp-agent"
_REMOTE_KEY = "isc_dhcp_agent_github"
_CHECK_EVERY = 300
_checking = {"on": False}


def _local_agent():
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_dist", "isc-dhcp-agent")
    try:
        return open(path, "rb").read()
    except OSError:
        return b""


def _ver(raw):
    import re

    m = re.search(rb'^AGENT_VERSION="([^"]+)"', raw or b"", re.M)
    return m.group(1).decode() if m else ""


def _fetch_github():
    """Background: download the newest agent from GitHub (once per hour), keep it in the cache."""
    import time

    from django.core.cache import cache

    try:
        import requests
        from django.conf import settings

        bust = {"_": str(int(time.time()))}  # raw.githubusercontent.com is CDN-cached per region; a unique query hits the origin
        r = requests.get(GITHUB_AGENT, params=bust, timeout=15,
                         headers={"Cache-Control": "no-cache"},
                         proxies=getattr(settings, "HTTP_PROXIES", None) or None)
        raw = r.content if r.status_code == 200 else b""
        ok = raw.startswith(b"#!") and _ver(raw)
        if ok:  # only a script that bash can parse
            import subprocess

            ok = subprocess.run(["bash", "-n"], input=raw, capture_output=True, timeout=10).returncode == 0
        cache.set(_REMOTE_KEY, {"raw": raw if ok else b"", "checked": time.time(),
                                "error": "" if ok else f"HTTP {r.status_code}"}, None)
    except Exception as e:
        cache.set(_REMOTE_KEY, {"raw": b"", "checked": time.time(), "error": type(e).__name__}, None)
    finally:
        _checking["on"] = False


def github_agent():
    """Cached GitHub copy {raw, checked, error}; starts a background check when older than an hour (never blocks)."""
    import threading
    import time

    from django.core.cache import cache

    try:
        data = cache.get(_REMOTE_KEY)
    except Exception:
        data = None
    if (not data or time.time() - data.get("checked", 0) > _CHECK_EVERY) and not _checking["on"]:
        _checking["on"] = True
        threading.Thread(target=_fetch_github, daemon=True).start()
    return data or {}


def agent_source():
    """(version, 'github'|'plugin', checked_epoch, error) of the agent NetBox offers."""
    gh = github_agent()
    local = _local_agent()
    gv = _ver(gh.get("raw"))
    if gv and _vkey(gv) > _vkey(_ver(local)):
        return gv, "github", gh.get("checked"), gh.get("error", "")
    return _ver(local), "plugin", gh.get("checked"), gh.get("error", "")


def agent_script():
    """(version, sha256, bytes) of the newest agent: GitHub copy when newer than the one bundled in this plugin."""
    import hashlib

    raw = _local_agent()
    gh = github_agent().get("raw") or b""
    if _ver(gh) and _vkey(_ver(gh)) > _vkey(_ver(raw)):
        raw = gh
    if not raw:
        return "", "", b""
    return _ver(raw), hashlib.sha256(raw).hexdigest(), raw


def _vkey(v):
    import re

    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def agent_outdated(server) -> bool:
    latest = agent_script()[0]
    return bool(latest and server.agent_version and _vkey(server.agent_version) < _vkey(latest))


CMDS = ("start", "stop", "restart", "update")
