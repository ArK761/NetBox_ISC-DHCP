"""Audit: collect file changes during a regeneration and store one event."""
import difflib
import threading
import time

from django.utils import timezone

from .models import AuditEvent

_local = threading.local()
KEEP = 10000
DIFF_LINES = 400


def start():
    _local.changes = []
    _local.t0 = time.monotonic()


def record(path, action, old_text, new_text, old_sha="", new_sha=""):
    ch = getattr(_local, "changes", None)
    if ch is None:
        return
    diff = ""
    if action == "update":
        lines = list(difflib.unified_diff((old_text or "").splitlines(), (new_text or "").splitlines(), "old", "new", n=1, lineterm=""))
        diff = "\n".join(lines[2:DIFF_LINES]) + ("\n…" if len(lines) > DIFF_LINES else "")
    ch.append({"path": path, "action": action, "old": old_sha[:12], "new": new_sha[:12], "diff": diff})


_LOCAL = {"127.0.0.1", "::1"}


def client_ip(request):
    """Real client IP. Behind the local reverse proxy (Apache/nginx on the same host) take X-Forwarded-For / X-Real-IP;
    from any other address the header is ignored (cannot be spoofed from outside)."""
    ip = request.META.get("REMOTE_ADDR", "")
    if ip in _LOCAL:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "") or request.META.get("HTTP_X_REAL_IP", "")
        if fwd:
            return fwd.split(",")[-1].strip()  # the proxy appends the address it saw as the last entry
    return ip


def current_user():
    try:
        from netbox.context import current_request

        req = current_request.get()
        if req is not None and getattr(req, "user", None) is not None and req.user.is_authenticated:
            return req.user.username, client_ip(req)
        if req is not None:
            return "", client_ip(req)
    except Exception:
        pass
    return "", ""


def finish(cause, always=False):
    """Store the regeneration event (only when files changed, unless always)."""
    ch = getattr(_local, "changes", None) or []
    t0 = getattr(_local, "t0", time.monotonic())
    _local.changes = None
    from . import build, versions

    mh = build.manifest_hash()
    versions.ensure(mh)
    versions.remember_dirs()
    if not ch and not always:
        return None

    user, ip = current_user()
    ev = AuditEvent.objects.create(time=timezone.now(), kind="regen", user=user, client_ip=ip, cause=cause[:4000],
                                   duration_ms=int((time.monotonic() - t0) * 1000), manifest_hash=mh, changes=ch)
    prune()
    return ev


def download(request, path=None):
    """Manifest fetch = new event; file fetches of the same client are added to its latest event (30 min)."""
    from . import build

    from .agent import server_for

    ip = client_ip(request)
    user = request.user.username if request.user.is_authenticated else ""
    srv = server_for(request)
    sname = srv.name if srv else ""
    now = timezone.now()
    if path is None:
        AuditEvent.objects.create(time=now, kind="download", user=user, client_ip=ip, server=sname, cause="manifest", manifest_hash=build.manifest_hash())
        prune()
        return
    ev = AuditEvent.objects.filter(kind="download", client_ip=ip, user=user, time__gte=now - timezone.timedelta(minutes=30)).first()
    if ev is None:
        from ..i18n import t

        ev = AuditEvent.objects.create(time=now, kind="download", user=user, client_ip=ip, server=sname, cause=t("aud.dl_files"), manifest_hash=build.manifest_hash())
    ev.changes = (ev.changes or []) + [{"path": path, "action": "download"}]
    ev.save(update_fields=["changes"])


def prune():
    ids = list(AuditEvent.objects.order_by("-time").values_list("pk", flat=True)[KEEP:KEEP + 1000])
    if ids:
        AuditEvent.objects.filter(pk__in=ids).delete()
