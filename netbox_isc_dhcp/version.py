"""Plugin version and the git commit it was installed from (pip VCS installs record it)."""
import json
from importlib import metadata

from . import __version__


def commit_id() -> str:
    try:
        raw = metadata.distribution("netbox-isc-dhcp").read_text("direct_url.json")
        return (json.loads(raw).get("vcs_info") or {}).get("commit_id", "") if raw else ""
    except Exception:
        return ""


def label() -> str:
    c = commit_id()
    return f"ISC DHCP v{__version__}" + (f" · {c}" if c else "")
