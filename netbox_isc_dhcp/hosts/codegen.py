"""Content of the group files: Jinja code (shared for all groups) rendered with the hosts of one group."""
from types import SimpleNamespace

from ..dhcp_tables import default_table_template
from ..renderer import RenderError, render

DEFAULT_DYNAMIC = default_table_template()  # owner's class format (golden-tested)

DEFAULT_STATIC = '''{% for h in hosts %}
host {{ h.host }} {
      hardware ethernet {{ h.mac }};
      fixed-address {{ h.ip }};
{% if h.hostname %}
      option host-name {{ h.hostname }};
{% endif %}
        }
{% endfor %}
'''

HOSTNAME_CHOICES = ("name", "host", "none")  # or a field key of the object


def context(hg, built, enabled=True):
    """Variables of both files. Dynamic: class_name, pairs (.name .mac), tenants (.name .macs).
    Static: class_name, hosts (.host .name .mac .ip .hostname)."""
    dyn = built["dynamic"]["rows"] if enabled else []
    sta = built["static"]["rows"] if enabled else []
    pairs = [SimpleNamespace(name=base, mac=m, host=h) for h, m, base in dyn]
    by = {}
    for h, m, base in dyn:
        by.setdefault(base, [])
        if m not in by[base]:
            by[base].append(m)
    tenants = [SimpleNamespace(name=n, macs=ms) for n, ms in by.items()]
    hosts = [SimpleNamespace(host=r[0], mac=r[1], ip=r[2], name=r[3], hostname=r[4]) for r in sta]
    return {"class_name": hg.name, "pairs": pairs, "tenants": tenants, "hosts": hosts}


def render_files(hg, built, codes):
    """{kind: (text, error)} for both files."""
    ctx = context(hg, built, hg.enabled)
    out = {}
    for kind in ("dynamic", "static"):
        try:
            out[kind] = (render(codes[kind], ctx), "")
        except RenderError as exc:
            out[kind] = ("", str(exc))
    return out


def code_errors(code) -> str:
    """Render the code on sample data (several MACs, no hosts) -> first error or ''."""
    sample = {"dynamic": {"rows": [("A_1", "AA:BB:CC:00:00:01", "A"), ("A_2", "AA:BB:CC:00:00:02", "A"), ("B", "AA:BB:CC:00:00:03", "B")]},
              "static": {"rows": [("C", "AA:BB:CC:00:00:04", "10.0.0.4", "C", "C"), ("D_1", "AA:BB:CC:00:00:05", "10.0.0.5", "D", None)]}}
    hg = SimpleNamespace(name="Sample", enabled=True)
    for b in (sample, {"dynamic": {"rows": []}, "static": {"rows": []}}):
        try:
            render(code, context(hg, b))
        except RenderError as exc:
            return str(exc)
    return ""
