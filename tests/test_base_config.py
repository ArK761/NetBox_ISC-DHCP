import re

import pytest

from netbox_isc_dhcp.base_config import clean_groups, render_base_config, subnet_includes
from netbox_isc_dhcp.renderer import RenderError, render

GROUPS = ["AllowALL", "WorkStation"]
PREFIXES = ["10.20.10.0/24", "10.20.2.0/24", "192.168.3.16/28", "10.0.0.0/8", "10.20.2.0/24"]


def includes(text):
    return re.findall(r'^\s*include "([^"]+)";', text, flags=re.M)


def test_prefix_includes_sorted_numerically_and_deduped():
    out = [i.file for i in subnet_includes(PREFIXES)]
    assert out == ["10.0.0.0_CFG", "10.20.2.0_CFG", "10.20.10.0_CFG", "192.168.3.16_CFG"]


def test_invalid_and_ipv6_prefixes_skipped():
    assert subnet_includes(["garbage", "2001:db8::/64", "10.0.0.5/24"]) == []


def test_unsafe_group_names_dropped():
    assert clean_groups(["Good_1", "../etc/passwd", 'a"b', "Good_1", "x y"]) == ["Good_1"]


def test_base_config_include_order_tables_before_subnets():
    inc = includes(render_base_config(GROUPS, PREFIXES))
    assert inc == [
        "/opt/dhcp/TABLE/AllowALL_Table",
        "/opt/dhcp/TABLE/AllowALL_StaticTable",
        "/opt/dhcp/TABLE/WorkStation_Table",
        "/opt/dhcp/TABLE/WorkStation_StaticTable",
        "/opt/dhcp/TABLE/Netbox_Devices-MAC",
        "/opt/dhcp/SUBNET/10.0.0.0_CFG",
        "/opt/dhcp/SUBNET/10.20.2.0_CFG",
        "/opt/dhcp/SUBNET/10.20.10.0_CFG",
        "/opt/dhcp/SUBNET/192.168.3.16_CFG",
    ]


def test_static_text_is_preserved_verbatim():
    out = render_base_config(GROUPS, PREFIXES)
    assert "authoritative;" in out
    assert "dhcp-cache-threshold=40;" in out
    assert "subnet 192.168.0.0 netmask 255.255.255.0 {}" in out
    assert out.count("binary-to-ascii") == 6
    assert "{%" not in out and "{{" not in out


def test_no_groups_no_prefixes_still_valid():
    inc = includes(render_base_config([], []))
    assert inc == ["/opt/dhcp/TABLE/Netbox_Devices-MAC"]


def test_custom_template_and_dirs():
    out = render_base_config(
        ["G"], ["10.1.0.0/24"], template_text="{% for p in prefixes %}{{ subnet_dir }}/{{ p.file }}\n{% endfor %}",
        subnet_dir="/x/",
    )
    assert out == "/x/10.1.0.0_CFG\n"


def test_missing_variable_is_an_error_not_empty():
    with pytest.raises(RenderError):
        render("{{ nope }}", {})


def test_template_syntax_error_reported():
    with pytest.raises(RenderError):
        render("{% for %}", {})


def test_sandbox_blocks_dangerous_access():
    with pytest.raises(RenderError):
        render("{{ ''.__class__.__mro__ }}", {})
