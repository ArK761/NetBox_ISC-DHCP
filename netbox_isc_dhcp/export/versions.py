"""CFG numbers: every CFG set (manifest hash) gets <dd.mm.yy>_<NNN> (NNN = order of the day, from 000)."""
from django.db import IntegrityError, transaction
from django.utils import timezone


def ensure(manifest_hash):
    """CfgVersion of this set (created now if it is new)."""
    from .models import CfgVersion

    if not manifest_hash:
        return None
    v = CfgVersion.objects.filter(hash=manifest_hash).first()
    if v is not None:
        return v
    now = timezone.localtime()
    day = now.strftime("%d.%m.%y")
    n = CfgVersion.objects.filter(label__startswith=day + "_").count()
    try:
        with transaction.atomic():
            return CfgVersion.objects.create(hash=manifest_hash, label=f"{day}_{n:03d}", created=now)
    except IntegrityError:
        return CfgVersion.objects.filter(hash=manifest_hash).first()


def label(manifest_hash, create=False) -> str:
    from .models import CfgVersion

    if not manifest_hash:
        return ""
    v = ensure(manifest_hash) if create else CfgVersion.objects.filter(hash=manifest_hash).only("label").first()
    return v.label if v else manifest_hash[:12]


def labels() -> dict:
    from .models import CfgVersion

    return dict(CfgVersion.objects.values_list("hash", "label"))


def remember_dirs():
    """Add the current managed directories to PluginSettings.agent_dirs (old files there are deleted by the agent)."""
    from ..models import settings_obj
    from .models import ExportFile

    st = settings_obj()
    if st is None:
        return
    now = {p.rsplit("/", 1)[0] for p in ExportFile.objects.exclude(area="conf").values_list("path", flat=True)}
    new = sorted(set(st.agent_dirs or []) | now)
    if new != sorted(st.agent_dirs or []):
        type(st).objects.filter(pk=st.pk).update(agent_dirs=new)
