"""The command list of the agent and of the plugin must be the same (1:1)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "netbox_isc_dhcp"


def _agent_list():
    src = (ROOT / "agent_dist" / "isc-dhcp-agent").read_text()
    m = re.search(r"^AGENT_COMMANDS=\((.*)\)$", src, re.M)
    return re.findall(r'"([^"]+)"|(\S+)', m.group(1))


def test_agent_and_plugin_commands_equal():
    agent = tuple(a or b for a, b in _agent_list())
    py = (ROOT / "export" / "agent.py").read_text()
    m = re.search(r"^AGENT_COMMANDS = \((.*?)\n\)", py, re.M | re.S)
    plugin = tuple(re.findall(r'"([^"]+)"', m.group(1)))
    assert agent == plugin


def test_every_command_has_texts():
    from netbox_isc_dhcp.i18n import TR

    py = (ROOT / "export" / "agent.py").read_text()
    m = re.search(r"^AGENT_COMMANDS = \((.*?)\n\)", py, re.M | re.S)
    for c in re.findall(r'"([^"]+)"', m.group(1)):
        k = c.replace(" ", "_")
        assert f"cmd.{k}.do" in TR and f"cmd.{k}.lim" in TR, c


def test_backup_path():
    from netbox_isc_dhcp.base_config import is_backup_path as ok

    assert ok("/opt/BCK") and ok("/opt/dhcp/bck/")
    for p in ("/", "/opt", "/opt/", "/usr", "/var/lib", "/etc/dhcp", "/opt/../usr", "/opt/a b", "/opt/./x", "opt/BCK"):
        assert not ok(p), p
