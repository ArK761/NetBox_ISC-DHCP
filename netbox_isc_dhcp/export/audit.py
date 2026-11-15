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


def current_user():
    try:
        from netbox.context import current_request

        req = current_request.get()
        if req is not None and getattr(req, "user", None) is not None and req.user.is_authenticated:
            return req.user.username, req.META.get("REMOTE_ADDR", "")
        if req is not None:
            return "", req.META.get("REMOTE_ADDR", "")
    except Exception:
        pass
    return "", ""


def finish(cause, always=False):
    """Store the regeneration event (only when files changed, unless always)."""
    ch = getattr(_local, "changes", None) or []
    t0 = getattr(_local, "t0", time.monotonic())
    _local.changes = None
    if not ch and not always:
        return None
    from . import build

    user, ip = current_user()
    ev = AuditEvent.objects.create(time=timezone.now(), kind="regen", user=user, client_ip=ip, cause=cause[:4000],
                                   duration_ms=int((time.monotonic() - t0) * 1000), manifest_hash=build.manifest_hash(), changes=ch)
    prune()
    return ev


def download(request, path=None):
    """Manifest fetch = new event; file fetches of the same client are added to its latest event (30 min)."""
    from . import build

    ip = request.META.get("REMOTE_ADDR", "")
    user = request.user.username if request.user.is_authenticated else ""
    now = timezone.now()
    if path is None:
        AuditEvent.objects.create(time=now, kind="download", user=user, client_ip=ip, cause="manifest", manifest_hash=build.manifest_hash())
        prune()
        return
    ev = AuditEvent.objects.filter(kind="download", client_ip=ip, user=user, time__gte=now - timezone.timedelta(minutes=30)).first()
    if ev is None:
        ev = AuditEvent.objects.create(time=now, kind="download", user=user, client_ip=ip, cause="files", manifest_hash=build.manifest_hash())
    ev.changes = (ev.changes or []) + [{"path": path, "action": "download"}]
    ev.save(update_fields=["changes"])


def prune():
    ids = list(AuditEvent.objects.order_by("-time").values_list("pk", flat=True)[KEEP:KEEP + 1000])
    if ids:
        AuditEvent.objects.filter(pk__in=ids).delete()
