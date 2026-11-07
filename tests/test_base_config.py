import re

from netbox_isc_dhcp.base_config import (
    default_static_text,
    render_base_config,
    render_dynamic_part,
    split_groups,
    subnet_includes,
)

GROUPS = ["AllowALL", "WorkStation"]
PREFIXES = ["10.20.10.0/24", "10.20.2.0/24", "192.168.3.16/28", "10.0.0.0/8", "10.20.2.0/24"]


def includes(text):
    return re.findall(r'^\s*include "([^"]+)";', text, flags=re.M)


def test_prefix_includes_sorted_numerically_and_deduped():
    assert [i.file for i in subnet_includes(PREFIXES)] == [
        "10.0.0.0_CFG", "10.20.2.0_CFG", "10.20.10.0_CFG", "192.168.3.16_CFG"]


def test_invalid_and_ipv6_prefixes_skipped():
    assert subnet_includes(["garbage", "2001:db8::/64", "10.0.0.5/24"]) == []


def test_unsafe_group_names_reported():
    ok, bad = split_groups(["Good_1", "../etc/passwd", 'a"b', "Good_1", "x y"])
    assert ok == ["Good_1"] and bad == ["../etc/passwd", 'a"b', "x y"]


def test_include_order_tables_before_subnets():
    inc = includes(render_dynamic_part(GROUPS, PREFIXES))
    assert inc == [
        "/opt/dhcp/TABLE/AllowALL_Table", "/opt/dhcp/TABLE/AllowALL_StaticTable",
        "/opt/dhcp/TABLE/WorkStation_Table", "/opt/dhcp/TABLE/WorkStation_StaticTable",
        "/opt/dhcp/TABLE/Netbox_Devices-MAC",
        "/opt/dhcp/SUBNET/10.0.0.0_CFG", "/opt/dhcp/SUBNET/10.20.2.0_CFG",
        "/opt/dhcp/SUBNET/10.20.10.0_CFG", "/opt/dhcp/SUBNET/192.168.3.16_CFG",
    ]


def test_static_text_is_verbatim_even_with_template_syntax():
    text = "# {{ not a template }} {% nor this %}\nauthoritative;\n"
    out = render_base_config(text, GROUPS, PREFIXES)
    assert out.startswith(text.rstrip("\n") + "\n\n")
    assert "{{ not a template }}" in out


def test_default_static_text_has_no_includes_and_keeps_primary():
    s = default_static_text()
    assert "include " not in s
    assert "subnet 192.168.0.0 netmask 255.255.255.0 {}" in s
    assert s.count("binary-to-ascii") == 6


def test_empty_data_still_valid():
    assert includes(render_dynamic_part([], [])) == ["/opt/dhcp/TABLE/Netbox_Devices-MAC"]


def test_custom_dirs():
    out = render_dynamic_part([], ["10.1.0.0/24"], subnet_dir="/x/")
    assert '/x/10.1.0.0_CFG' in out
