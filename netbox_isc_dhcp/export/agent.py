"""Agent on a DHCP server: state of every server, gates (ISC version, failed set, staged rollout) and the plan of steps."""
from django.utils import timezone

from .models import ExportFile

INTERVALS = (10, 30, 60, 300, 600, 1200, 1800)  # seconds, chosen in CFG pluginu -> DHCP servery
FAILED = ("test_failed", "rolled_back", "failed")

# THE ONLY commands NetBox can send to the agent - 1:1 with AGENT_COMMANDS in agent_dist/isc-dhcp-agent (test checks it).
# Shown read-only in CFG pluginu -> DHCP servery. as_text() never writes a line that is not here; the agent ignores it anyway.
AGENT_COMMANDS = (
    "download", "bundle", "backup", "test", "restart", "on_test_fail", "delete",
    "cmd start", "cmd stop", "cmd restart", "cmd update", "cmd simfirst", "cmd restoreleases", "cmd delfirst", "settings_check", "agent_url", "agent_sha",
    "key", "interval", "report", "base", "dir", "conf_dir",
    "hash", "cfg", "mode", "server", "wait", "wait_for", "error", "disk", "restart_req", "check", "leases", "time_format", "test_server",
)
TIME_FORMATS = {"eu": ("DD.MM.RRRR-HH:MM", "%d.%m.%Y-%H:%M"), "iso": ("RRRR-MM-DD_HH:MM", "%Y-%m-%d_%H:%M"), "compact": ("RRRRMMDD-HHMMSS", "%Y%m%d-%H%M%S")}
# commands the agent runs: fixed, shown read-only on the Agent page (the agent runs only what its own ALLOWED_* lists allow)
TEST_CMD = "dhcpd -t -cf {conf}"
RESTART_CMD = "systemctl restart isc-dhcp-server"


def time_fmt(seconds=False):
    """strftime format of the admin's time format (CFG pluginu); seconds=True adds :SS when the format has none."""
    from ..models import settings_obj

    f = TIME_FORMATS.get(getattr(settings_obj(), "agent_time_format", "eu"), TIME_FORMATS["eu"])[1]
    return f + ":%S" if seconds and "%S" not in f else f


def fmt_time(when, seconds=False):
    """datetime or unix time (int / digit string) -> local time in the admin's format; '' when unknown."""
    import datetime

    from django.utils import timezone

    if isinstance(when, (int, str)):
        if not str(when).isdigit():
            return ""
        when = datetime.datetime.fromtimestamp(int(when), tz=datetime.timezone.utc)
    return timezone.localtime(when).strftime(time_fmt(seconds)) if when else ""
LEASES_EVERY = (0, 15, 30, 60, 180, 360, 720, 1440)  # minutes, 0 = off
LEASES_KEEP = (6, 12, 24, 48, 72, 96, 168)
# what the agent does on its own (no command from NetBox) - shown under the list
AGENT_SELF = ("default_fix", "apparmor", "kill_stray", "keep_up", "pidfile", "dedupe", "watch", "leases", "reboot")


def command_rows():
    """[(command, what it does, limit on the agent side)] for the read-only list in the plugin (i18n cmd.<name>.do / .lim)."""
    from ..i18n import t

    out = []
    for c in AGENT_COMMANDS:
        k = c.replace(" ", "_")
        out.append((c, t(f"cmd.{k}.do"), t(f"cmd.{k}.lim")))
    return out


def self_rows():
    from ..i18n import t

    return [t(f"self.{k}") for k in AGENT_SELF]


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


TEST_VERIFY_S = 60  # the test server must run the new CFG this long (dhcpd up, hash = NetBox) before production gets it


def test_server():
    """The enabled test DHCP server with an agent (only one may exist), or None."""
    from .models import DHCPServer

    return DHCPServer.objects.filter(is_test=True, enabled=True, last_seen__isnull=False).order_by("pk").first()


def cfg_proven(manifest_hash, exclude=None):
    """Some enabled server already runs this CFG set OK (deployed, tested, dhcpd running): the test server need not hold the others back."""
    from .models import DHCPServer

    qs = DHCPServer.objects.filter(enabled=True, last_result="ok", last_hash=manifest_hash, running_hash=manifest_hash, dhcpd_running=True)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.exists()


def test_kick(server, manifest_hash, client_ip=""):
    """Test server holds this CFG (deployed OK) but it is not verified and dhcpd is stopped from NetBox: start it for the check
    (test_verify then stops it again). Returns True when a start was queued."""
    from ..i18n import t
    from . import versions
    from .models import AuditEvent

    if (server is None or not server.is_test or not server.enabled or server.agent_cmd or server.test_ok_hash == manifest_hash
            or server.last_result != "ok" or server.last_hash != manifest_hash or server.running_hash != manifest_hash
            or server.dhcpd_running is not False or server.dhcpd_by != "admin"):
        return False
    server.agent_cmd = f"start:{timezone.now().strftime('%Y%m%d%H%M%S')}"
    server.save(update_fields=["agent_cmd"])
    AuditEvent.objects.create(time=timezone.now(), kind="agent", server=server.name, client_ip=client_ip, level="info",
                              manifest_hash=manifest_hash, cause=t("aud.test_kick", cfg=versions.label(manifest_hash)))
    return True


def test_verify(server, manifest_hash, check, client_ip=""):
    """Test server: CFG deployed OK, hash = NetBox and dhcpd running >= TEST_VERIFY_S -> verified (production may get it),
    dhcpd on the test server is stopped (NetBox command, visible in the Audit). Returns True when it was verified now."""
    from ..i18n import t
    from . import versions
    from .models import AuditEvent

    if server is None or not server.is_test or not server.enabled or server.test_ok_hash == manifest_hash:
        return False
    from datetime import timedelta

    proven = cfg_proven(manifest_hash, exclude=server)  # runs OK elsewhere already: test + start is enough, no 60 s wait
    old = timezone.now() - timedelta(seconds=0 if proven else TEST_VERIFY_S)
    ok = (server.last_result == "ok" and server.last_hash == manifest_hash and server.running_hash == manifest_hash
          and server.dhcpd_running and server.disk_hash == check and server.last_report and server.last_report <= old
          and (server.dhcpd_since is None or server.dhcpd_since <= old))
    if not ok:
        return False
    server.test_ok_hash = manifest_hash
    fields = ["test_ok_hash"]
    if not server.agent_cmd and not (server.test_until and server.test_until > timezone.now()):  # admin's run time wins
        server.agent_cmd = f"stop:{timezone.now().strftime('%Y%m%d%H%M%S')}"
        server.stop_why = t("why.test_ok", cfg=versions.label(manifest_hash))
        fields += ["agent_cmd", "stop_why"]
    server.save(update_fields=fields)
    AuditEvent.objects.create(time=timezone.now(), kind="agent", server=server.name, client_ip=client_ip, level="info",
                              manifest_hash=manifest_hash, cause=t("aud.test_ok_proven" if proven else "aud.test_ok", cfg=versions.label(manifest_hash), s=TEST_VERIFY_S))
    return True


TEST_RUN_MIN = (5, 10, 20, 40, 60, 120)  # Start on the test server: how long dhcpd may run (max 2 h)


def test_timer(server, client_ip=""):
    """Test server started from NetBox for N minutes: time is up -> NetBox stops dhcpd (Audit). True when the stop was queued."""
    from ..i18n import t
    from .models import AuditEvent

    if server is None or not server.test_until or server.test_until > timezone.now():
        return False
    until = server.test_until
    server.test_until = None
    fields = ["test_until"]
    queued = False
    if server.dhcpd_running and not server.agent_cmd:
        server.agent_cmd = f"stop:{timezone.now().strftime('%Y%m%d%H%M%S')}"
        server.stop_why = t("why.timer", at=timezone.localtime(until).strftime("%H:%M"))
        fields += ["agent_cmd", "stop_why"]
        queued = True
    server.save(update_fields=fields)
    if queued:
        AuditEvent.objects.create(time=timezone.now(), kind="agent", server=server.name, client_ip=client_ip, level="info",
                                  cause=t("aud.test_timer_stop", name=server.name))
    return queued


def gate(server, manifest_hash):
    """(reason, [server names]) why this server must wait now, or ("", [])."""
    from ..models import settings_obj

    if server is None:
        return "", []
    if server.isc_version == "none":
        return "isc_missing", []
    if server.takeover == "foreign":
        return "takeover", []  # original DHCP found: no CFG until the admin confirms the backup + overwrite
    first = first_server()
    if isc_mismatch() and (first is None or server.pk != first.pk):
        return "isc_mismatch", [first.name] if first else []
    if server.last_result in FAILED and server.last_hash == manifest_hash:
        return "failed_same", []  # never send the set that already failed here again (no endless restore loop)
    test = test_server()
    if test is not None and server.pk != test.pk:  # test server: production gets the CFG only after the test server verified it (no release button)
        if test.test_ok_hash == manifest_hash or cfg_proven(manifest_hash):
            return "", []  # verified on the test server, or already running OK on a server: all production servers at once
        failed = test.last_hash == manifest_hash and test.last_result and test.last_result != "ok"
        return ("test_failed" if failed else "test_wait"), [test.name]
    if test is not None:
        return "", []  # the test server itself never waits for production servers (staged order ignored with a test server)
    st = settings_obj()
    if (st and st.staged_rollout) or running_mismatch():
        before = [s for s in enabled_servers() if s.order < server.order and s.last_seen]  # no agent yet = blocks nobody
        waiting = [s.name for s in before if not ((s.last_result == "ok" and s.last_hash == manifest_hash)
                                                  or s.released_hash == manifest_hash or s.isc_version == "none")]
        if waiting:
            return "staged", waiting
    return "", []


AUTOSYNC_MINUTES = (5, 15, 30, 60)


def autosync_due(server, manifest_hash):
    """Auto CFG sync (CFG pluginu -> DHCP servery): the server runs another CFG than NetBox -> push the full CFG
    after X minutes of mismatch or once a day at a fixed time. Never: a CFG that already failed here (the old CFG
    stays), dhcpd stopped from NetBox, no ISC, no CFG running yet. Returns the reason text for the Audit or ""."""
    from ..i18n import t
    from ..models import settings_obj

    if server is None:
        return ""
    now = timezone.now()
    mismatch = bool(server.running_hash) and server.running_hash != manifest_hash
    if not mismatch:
        if server.mismatch_since:
            server.mismatch_since = None
            server.save(update_fields=["mismatch_since"])
        return ""
    if not server.mismatch_since:
        server.mismatch_since = now
        server.save(update_fields=["mismatch_since"])
    st = settings_obj()
    mode = st.agent_autosync if st else "off"
    if mode not in ("after", "at") or server.isc_version == "none":
        return ""
    if server.last_result in FAILED and server.last_hash == manifest_hash:
        return ""  # this CFG failed here: the old one stays until a fixed CFG comes
    if server.dhcpd_by == "admin" and server.dhcpd_running is False:
        return ""  # stopped from NetBox
    mins = int((now - server.mismatch_since).total_seconds() // 60)
    if mode == "after":
        every = st.agent_autosync_min or 15
        if mins < every or (server.autosync_last and (now - server.autosync_last).total_seconds() < every * 60):
            return ""
        why = t("aud.autosync_after", name=server.name, min=mins)
    else:
        loc = timezone.localtime(now)
        try:
            hh, mm = (int(x) for x in (st.agent_autosync_at or "03:00").split(":"))
        except ValueError:
            return ""
        if (loc.hour, loc.minute) < (hh, mm):
            return ""
        if server.autosync_last and timezone.localtime(server.autosync_last).date() == loc.date():
            return ""  # once a day
        why = t("aud.autosync_at", name=server.name, at=st.agent_autosync_at, min=mins)
    server.autosync_last = now
    server.last_result = ""  # = Download again: the next plan is the full CFG
    server.save(update_fields=["autosync_last", "last_result"])
    return why


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

    if server is not None and server.last_result not in ("ok", "start_failed"):
        mode = "export"  # never reported OK (or the last set failed) -> full set until the first OK (start_failed = CFG is fine, only the service will not start)
    rows = list(ExportFile.objects.order_by("area", "path").values("path", "area", "sha256", "size"))
    want = {r["path"]: r for r in rows}
    dirs = managed_dirs()
    download = list(rows) if mode == "export" else [r for r in rows if have.get(r["path"]) != r["sha256"]]
    delete = sorted(p for p in have if p not in want and p.rsplit("/", 1)[0] in dirs)  # only inside the managed dirs
    if not download and not delete:
        return []
    conf = next((r["path"] for r in rows if r["area"] == "conf"), "")
    st = settings_obj()
    from ..base_config import is_backup_path

    backup = st.agent_backup_dir if st and is_backup_path(st.agent_backup_dir) else BACKUP_DIR  # only below /opt
    cur = sorted({r["path"].rsplit("/", 1)[0] for r in rows if r["area"] != "conf"})
    steps = [{"op": "backup", "paths": ([conf] if conf else []) + cur, "to": backup}]
    # included files first, dhcpd.conf last: dhcpd.conf never points to a file that is not there yet
    for r in sorted(download, key=lambda r: r["area"] == "conf"):
        steps.append({"op": "download", "path": r["path"], "sha256": r["sha256"], "size": r["size"], "url": file_url(r["path"])})
    steps.append({"op": "test", "cmd": TEST_CMD.replace("{conf}", conf), "on_fail": "restore"})
    steps.append({"op": "restart", "cmd": RESTART_CMD, "on_fail": "restore"})
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

    def allowed(line):  # only commands from AGENT_COMMANDS go out
        key, _, rest = line.partition("\t")
        return (f"cmd {rest.split(chr(9), 1)[0]}" if key == "cmd" else key) in AGENT_COMMANDS

    return "\n".join(x for x in lines if allowed(x)) + "\n"


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
            raw = t(key) + raw[len(prefix):]
            break
    return raw.replace(" | logged in:", " | " + t("why.logged_in"))


_SVC = (  # agent service reason (English) -> i18n key
    ("IPv6 server (dhcpd6) fails:", "svc.v6"),
    ("is missing: the service starts IPv4 AND IPv6 - set", "svc.nodefault"),
    ("has an empty INTERFACESv4: the service starts IPv4 AND IPv6 - set", "svc.emptyv4"),
)


def svc_text(raw):
    """Translate the agent's reason why the DHCP service is not active (plugin language)."""
    from ..i18n import t

    for frag, key in _SVC:
        raw = raw.replace(frag, t(key))
    return raw


_WARN = ("aud.ag_dhcpd_down", "aud.ag_isc_none", "aud.svc_bad", "aud.svc_state", "aud.insecure", "aud.dup", "aud.ag_agent_stop_auto", "aud.disk_warn", "aud.reboot_down")
_INFO = ("aud.reboot_up", "aud.reboot_stopped", "aud.svc_admin_off", "aud.disk_info", "aud.disk_ok", "aud.first_leases", "aud.leases_copy", "aud.ag_first", "aud.ag_updated", "aud.ag_isc_new", "aud.ag_isc_changed", "aud.fix", "aud.svc_ok", "aud.fail_cleared",
         "aud.secure", "aud.ag_agent_start_auto", "aud.ag_agent_start_nb", "aud.ag_agent_stop_nb", "aud.cmd_done")


def _level(msgs, failed=False):
    """Severity of an agent Audit row from the messages it holds: warn (red) > info (yellow) > ok (green)."""
    from ..i18n import t

    def hit(keys):
        pre = [t(k).split("{")[0] for k in keys]
        return any(p and m.startswith(p) for m in msgs for p in pre)

    if failed or hit(_WARN):
        return "warn"
    return "info" if hit(_INFO) else "ok"


def _ack(server, match, state, text):
    """Mark admin Audit rows (command / setting) as carried out by this server's agent (the frame in the Audit)."""
    from .models import AuditEvent

    n = 0
    for e in AuditEvent.objects.filter(kind="admin", pending__has_key=server.name).order_by("-id")[:50]:
        p = (e.pending or {}).get(server.name) or {}
        if p.get("s") == "wait" and match(p):
            p.update(s=state, t=timezone.now().isoformat(), x=text)
            e.pending[server.name] = p
            e.save(update_fields=["pending"])
            n += 1
    return n


DISK_WARN, DISK_CRIT = 60, 85  # disk usage: green < 60 %, yellow 60-85 % (clean up), red >= 85 % (critical)


def parse_disk(raw):
    """'mount:pct,...' from the agent -> [(mount, pct)]; None when the agent sent nothing usable."""
    out = []
    for part in raw.split(","):
        m, _, p = part.rpartition(":")
        m = "".join(c for c in m if c.isalnum() or c in "/._-")[:100]
        if m.startswith("/") and p.isdigit() and int(p) <= 100:
            out.append((m, int(p)))
    return out or None


def disk_level(stored):
    """ok | info (yellow) | warn (red) for the fullest file system; '' = unknown."""
    du = parse_disk(stored or "")
    if not du:
        return ""
    top = max(p for _, p in du)
    return "warn" if top >= DISK_CRIT else ("info" if top >= DISK_WARN else "ok")


def disk_rows(stored):
    """[(mount, pct, level)] for the server row."""
    return [(m, p, "warn" if p >= DISK_CRIT else ("info" if p >= DISK_WARN else "ok")) for m, p in (parse_disk(stored or "") or [])]


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
    pid = "".join(c for c in str(data.get("dhcpd_pid", ""))[:10] if c.isdigit())
    svc = "".join(c for c in str(data.get("svc", ""))[:20] if c.isalnum() or c in "-_")
    if svc in ("activating", "deactivating", "reloading", "refreshing"):
        svc = ""  # a moment during a start/stop: not a state worth a warning (the next contact brings the real one)
    svc_why = str(data.get("svc_why", ""))[:300]
    dup = str(data.get("dup", ""))[:200]
    insecure = str(data.get("insecure", "")) == "1"

    first = server.last_seen is None
    msgs, changes = [], []
    manual_msg = ""
    cmd_failed = False
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
    if event.startswith("reboot_") and isc != "none" and dhcpd is not None:  # the server booted: dhcpd started by the system = normal
        if event == "reboot_stopped":  # test server stopped from NetBox before the reboot: the agent stopped it again
            msgs.append(t("aud.reboot_stopped"))
            server.dhcpd_by = "admin"
        elif event == "reboot_up":
            msgs.append(t("aud.reboot_up", pid=pid or "?"))
            server.dhcpd_by = "boot"
        else:
            msgs.append(t("aud.reboot_down"))
            server.dhcpd_by = "admin" if server.dhcpd_by == "admin" else "boot"
        server.dhcpd_since, server.dhcpd_why, server.test_until = timezone.now(), "", None
    elif isc != "none" and dhcpd is not None and (dhcpd != server.dhcpd_running or first or server.isc_version in ("", "none")):
        why = str(data.get("dhcpd_why", ""))[:300]
        by_netbox = server.agent_cmd.split(":", 1)[0] in ("start", "stop", "restart") or bool(server.restart_req)
        if event.startswith("manual"):  # NOT through NetBox: own highlighted Audit row
            manual_msg = t("aud.ag_" + event) + (f" – {why_text(why)}" if why else "")
        elif event in ("agent_start", "agent_stop"):
            msgs.append(t("aud.ag_" + event + ("_nb" if by_netbox else "_auto"))
                        + (f" – {t('why.label')}: {server.stop_why}" if event == "agent_stop" and by_netbox and server.stop_why else ""))
            if event == "agent_stop":
                server.stop_why = ""
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
    if event == "manual_restart" and isc != "none" and not (pid and pid == server.dhcpd_pid):  # still running, new PID, not the agent: restarted by hand (same PID = already recorded)
        why = str(data.get("dhcpd_why", ""))[:300]
        manual_msg = t("aud.ag_manual_restart", old=server.dhcpd_pid or "?", new=pid or "?") + (f" – {why_text(why)}" if why else "")
        server.dhcpd_since, server.dhcpd_by, server.dhcpd_why = timezone.now(), "manual", why
    if event == "agent_restart" and isc != "none":  # the running dhcpd (new PID) was restarted by the agent: not "by hand" any more
        pending = server.agent_cmd.split(":", 1)[0] in ("start", "stop", "restart") or bool(server.restart_req)
        server.dhcpd_since, server.dhcpd_why = timezone.now(), ""
        server.dhcpd_by = "admin" if pending else "agent"
    done = str(data.get("cmd_done", ""))[:200]  # <id>:<ok|failed>:<text>
    if done and server.agent_cmd and done.split(":", 1)[0] == server.agent_cmd.split(":", 1)[1]:
        _, res, *txt = done.split(":", 2) + [""]
        cmd_failed = res != "ok"
        if res == "ok" and server.agent_cmd.startswith("restoreleases:"):
            server.leases_restored = f"{int(timezone.now().timestamp())}|{(txt[0] if txt else '')[:300]}"
        if res == "ok" and server.agent_cmd.startswith("delfirst:"):  # original backups deleted: nothing of the original DHCP is shown any more
            server.first_leases = server.leases_kept = server.leases_restored = server.first_cfg = ""
        if res == "ok" and server.agent_cmd.startswith("simfirst:"):  # agent cleared its state: NetBox side of a first installation
            server.takeover, server.takeover_info = "foreign", t("srv.sim_info")
            server.first_leases = server.leases_kept = server.leases_restored = ""
            server.last_result = ""
        if res == "ok" and server.agent_cmd.split(":", 1)[0] in ("start", "stop", "restart"):
            if server.dhcpd_by != "admin":
                server.dhcpd_since = timezone.now()
            server.dhcpd_by = "admin"
        if not _ack(server, lambda p: p.get("id") == server.agent_cmd.split(":", 1)[1], "ok" if res == "ok" else "failed", (txt[0] if txt else "")[:150]):
            # no admin row waits for it (older plugin row): say it here; otherwise the result is in the admin row's frame only (no duplicate)
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
    if dup:
        msgs.append(t("aud.dup", txt=dup))
    if insecure != server.agent_insecure and (insecure or server.last_seen):
        msgs.append(t("aud.insecure") if insecure else t("aud.secure"))
    server.agent_insecure = insecure
    fix = str(data.get("fix", ""))[:300]
    if fix:
        msgs.append(t("aud.fix", txt=fix))
    if svc and (svc != server.svc_state or (svc not in ("active", "none") and svc_why and svc_why != server.svc_why)):
        if svc in ("active", "none"):
            if server.svc_state not in ("", "active", "none"):
                msgs.append(t("aud.svc_ok", svc=svc))
        elif server.dhcpd_by == "admin" and dhcpd is False:  # stopped from NetBox (button / test server): planned, not a fault
            msgs.append(t("aud.svc_admin_off", svc=svc))
        else:
            msgs.append(t("aud.svc_bad", svc=svc, why=svc_text(svc_why)) if svc_why else t("aud.svc_state", svc=svc))
    if svc:
        server.svc_state, server.svc_why = svc, ("" if svc in ("active", "none") else svc_why)
    # the agent says dhcpd runs the CFG of the last (start) failure: that old "failed" is not true any more (dhcpd -t failures stay)
    if dhcpd and running and running == server.last_hash and server.last_result in ("failed", "start_failed"):
        server.last_result = "ok"
        msgs.append(t("aud.fail_cleared"))
    server.last_seen = timezone.now()
    server.dhcpd_pid = pid if dhcpd else ""
    if dhcpd is False and server.test_until and not server.agent_cmd.startswith("start:"):  # (Start still waiting = not down yet)  # dhcpd went down (Stop, by hand, crash): the run timer of the test server ends with it
        server.test_until = None
    fields = {"leases": "agent_leases", "time_format": "agent_time_format", "interval": "interval"}
    applied = {fields[x] for x in str(data.get("applied", "")).split(",") if x in fields}  # settings the agent took over (1.19.3+)
    if applied:
        _ack(server, lambda p: p.get("f") in applied, "ok", "")
    fl = str(data.get("first_leases", ""))[:400]
    if fl and fl != server.first_leases and len(fl.split("|")) == 4 and fl.split("|")[0].isdigit():
        server.first_leases = fl
        _t, n, sha, where = fl.split("|")
        msgs.append(t("aud.first_leases", n=n, sha=sha[:12], path=where))
    eff = str(data.get("eff", ""))[:2000]
    if eff:  # agent 1.30.0+: the settings it really uses (back-check)
        server.agent_eff = "".join(ch for ch in eff if ch.isprintable())
        server.agent_eff_at = timezone.now()
    if "first_cfg" in data:  # agent 1.27.0+: backup of the original CFG (start_<time>) still on the server
        server.first_cfg = "".join(ch for ch in str(data.get("first_cfg", ""))[:1000] if ch.isalnum() or ch in "/._-:|,")
    lt = str(data.get("leases_last", ""))
    if lt.isdigit() and len(lt) <= 12:  # unix time of the last periodic lease copy (agent 1.18.0+)
        import datetime as _dt

        server.leases_last = _dt.datetime.fromtimestamp(int(lt), tz=_dt.timezone.utc)
    ls = str(data.get("leases_sha", "")).lower()
    if len(ls) == 64 and all(c in "0123456789abcdef" for c in ls):
        server.leases_sha = ls
    lc = str(data.get("leases_copy", ""))[:200].split("|")  # <dir>|<old sha>|<new sha>: a new lease copy (Audit INFO)
    if len(lc) == 3 and lc[0]:
        name = "".join(ch for ch in lc[0] if ch.isalnum() or ch in ".-_:")
        msgs.append(t("aud.leases_copy", name=name, old=(lc[1][:12] or "—"), new=lc[2][:12]))
    du = parse_disk(str(data.get("disk_usage", ""))[:400])  # agent 1.25.0+: use% of its file systems
    if du is not None:
        du_txt = ",".join(f"{m}:{p}" for m, p in du)
        old_lv, new_lv = disk_level(server.disk_usage), disk_level(du_txt)
        if new_lv != old_lv and (new_lv != "ok" or old_lv):
            top = max(du, key=lambda x: x[1]) if du else ("/", 0)
            msgs.append(t("aud.disk_" + new_lv, mount=top[0], pct=top[1]))
        server.disk_usage = du_txt
    dh = str(data.get("disk_hash", "")).lower()
    if len(dh) == 64 and all(c in "0123456789abcdef" for c in dh):
        server.disk_hash = dh  # ONE hash of every CFG file on the server's disk (agent 1.16.0+)
    server.save(update_fields=["agent_eff", "agent_eff_at", "first_cfg", "stop_why", "test_until", "disk_usage", "leases_restored", "takeover", "takeover_info", "leases_kept", "first_leases", "leases_sha", "leases_last", "disk_hash", "agent_version", "isc_version", "running_hash", "dhcpd_running", "last_seen", "dhcpd_since", "dhcpd_by", "dhcpd_why", "dhcpd_pid", "svc_state", "svc_why", "last_result", "agent_insecure", "agent_cmd"])
    if not msgs:  # nothing changed: a status line at least once an hour
        from datetime import timedelta

        if not AuditEvent.objects.filter(kind="agent", server=server.name, time__gte=server.last_seen - timedelta(hours=1)).exclude(result="refused").exists():
            msgs.append(t("aud.ag_status", state=status_text(server)))
    if manual_msg:
        AuditEvent.objects.create(time=server.last_seen, kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                  result="manual", level="warn", manifest_hash=running, cause=manual_msg)
    if msgs:
        AuditEvent.objects.create(time=server.last_seen, kind="agent", server=server.name, client_ip=audit.client_ip(request),
                                  manifest_hash=running, cause="; ".join(msgs), changes=changes, level=_level(msgs, cmd_failed))


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


SETTINGS_CHECK = (1, 5, 10, 20)  # minutes: how often the agent reports the settings it really uses


def _vge(v, want):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3]) >= want
    except ValueError:
        return False


def agent_settings(server, st=None):
    """Settings NetBox sends to this agent (the same keys the plan carries): {key: value}."""
    from ..base_config import is_backup_path
    from ..models import BACKUP_DIR, settings_obj

    st = st or settings_obj()
    out = {"interval": str(st.agent_interval if st else 60)}
    if server is None or _vge(server.agent_version, (1, 18, 0)):
        bdir = st.agent_backup_dir if st and is_backup_path(st.agent_backup_dir) else BACKUP_DIR
        out["leases"] = f"{st.agent_leases_every if st else 60}|{st.agent_leases_keep if st else 72}|{bdir.rstrip('/')}/leases"
    if server is None or _vge(server.agent_version, (1, 19, 0)):
        out["time_format"] = (st.agent_time_format if st else "eu") or "eu"
    if server is None or _vge(server.agent_version, (1, 23, 0)):
        out["is_test"] = "1" if server is not None and server.is_test else "0"
    if server is None or _vge(server.agent_version, (1, 30, 0)):
        out["settings_check"] = str(st.agent_settings_check if st else 5)
    return out


def parse_eff(text):
    """'a=1;b=2;local=X:1,Y:2' -> ({a: 1, b: 2}, {X: 1, Y: 2})."""
    used, local = {}, {}
    for part in (text or "").split(";"):
        k, _, v = part.partition("=")
        if k == "local":
            for item in v.split(","):
                lk, _, lv = item.partition(":")
                if lk:
                    local[lk] = lv
        elif k:
            used[k] = v
    return used, local


def settings_rows(server, st=None):
    """[(key, NetBox value, agent value, ok)] + local {..} + checked time for the page / API."""
    want = agent_settings(server, st)
    used, local = parse_eff(server.agent_eff)
    rows = []
    for k, v in want.items():
        if k == "settings_check":
            continue  # the agent stores it, it does not report it back
        got = used.get(k)
        rows.append((k, v, got if got is not None else "", got is not None and got == v))
    return rows, local, used


def delfirst_block(server, manifest_hash):
    """Why 'delete the original backup' is disabled ('' = allowed): the NetBox CFG must run on the server (deployed, tested OK, dhcpd up)."""
    try:
        new_agent = tuple(int(x) for x in str(server.agent_version).split(".")[:3]) >= (1, 27, 0)
    except ValueError:
        new_agent = False
    if not new_agent:
        return "srv.df_agent"
    if not server.first_leases and not server.first_cfg:
        return "srv.df_none"
    if server.takeover == "foreign":
        return "srv.rl_takeover"
    if (server.disk_broken or server.last_result != "ok" or server.last_hash != manifest_hash
            or server.running_hash != manifest_hash or server.dhcpd_running is not True):
        return "srv.df_cfg"
    return ""


def restore_block(server, manifest_hash):
    """Why the 'put the original leases back' button is disabled ('' = allowed): the NetBox CFG must be deployed and tested OK."""
    if not server.first_leases:
        return "srv.rl_no_copy"
    if server.leases_restored:
        return "srv.rl_done"
    if server.takeover == "foreign":
        return "srv.rl_takeover"
    if server.disk_broken or server.last_result not in ("ok", "start_failed") or server.last_hash != manifest_hash:
        return "srv.rl_cfg"
    return ""
