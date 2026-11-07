import os
import re

import pytest

from netbox_isc_dhcp.dhcp_tables import build_file, default_static_template, normalize_mac, prepare

GOLDEN = os.environ.get(
    "WS_TABLE", "/root/.claude/uploads/bcbdb6b0-0bfa-5ea5-9582-099d35bea307/111d06b6-WorkStation_Table"
)


def test_normalize_mac():
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"
    assert normalize_mac("zz:bb") is None and normalize_mac(None) is None


def test_static_format_and_suffix():
    f = build_file("G", [("PC1", ["aa:bb:cc:dd:ee:01"], "10.0.0.5"),
                         ("PC2", ["aa:bb:cc:dd:ee:02", "aa:bb:cc:dd:ee:03", ""], "10.0.0.6")], default_static_template())
    assert f.text == (
        "host PC1 {\n      hardware ethernet AA:BB:CC:DD:EE:01;\n      fixed-address 10.0.0.5;\n"
        "      option host-name PC1;\n        }\n"
        "host PC2_1 {\n      hardware ethernet AA:BB:CC:DD:EE:02;\n      fixed-address 10.0.0.6;\n"
        "      option host-name PC2;\n        }\n"
        "host PC2_2 {\n      hardware ethernet AA:BB:CC:DD:EE:03;\n      fixed-address 10.0.0.6;\n"
        "      option host-name PC2;\n        }\n"
    )
    assert f.static_count == 2 and f.dynamic_count == 0
    assert "match if false;" in build_file("G", []).text


def test_tenant_without_mac_skipped_silently_but_invalid_mac_warns():
    d, s, w = prepare([("A", [None, ""], None), ("B", ["nonsense"], None)])
    assert d == [] and s == [] and w == ["B: invalid MAC 'nonsense' skipped"]


def test_duplicates_and_bad_values_skipped_with_warning():
    d, s, w = prepare([
        ("A", ["aa:aa:aa:aa:aa:01"], "10.0.0.1"),
        ("B", ["aa:aa:aa:aa:aa:01"], None),          # MAC taken
        ("C", ["aa:aa:aa:aa:aa:03"], "10.0.0.1"),    # IP taken
        ("D", ["aa:aa:aa:aa:aa:04"], "x.y"),         # bad IP
        ("E F", ["aa:aa:aa:aa:aa:05"], None),        # bad name
    ])
    assert [t.name for t in s] == ["A"] and d == []
    assert len(w) == 5 - 1 + 0 or len(w) == 4


def test_multi_mac_mismatch_does_not_flag_own_macs():
    f = build_file("G", [("PC1", ["aa:aa:aa:aa:aa:01", "aa:aa:aa:aa:aa:02"], None)])
    assert '((option host-name = "PC1") and (substring(hardware, 1, 6) != AA:AA:AA:AA:AA:01) and ' \
           '(substring(hardware, 1, 6) != AA:AA:AA:AA:AA:02))' in f.text


@pytest.mark.skipif(not os.path.exists(GOLDEN), reason="original WorkStation_Table not available")
def test_regenerates_original_workstation_table_exactly_for_single_mac_tenants():
    text = open(GOLDEN, encoding="utf-8").read()
    pos = re.findall(r'= ([0-9A-F:]{17}) and option host-name = "([^"]+)"\)', text)
    assert len(pos) > 1000
    by_name: dict[str, list[str]] = {}
    for mac, name in pos:
        by_name.setdefault(name, []).append(mac)
    raw = [(n, m, None) for n, m in by_name.items()]
    out = build_file("WorkStation", raw).text
    orig_class, orig_mis = text.split(' class "MismatchedClients"')
    new_class, new_mis = out.split(' class "MismatchedClients"')
    assert new_class == orig_class                               # whole WorkStation class is byte-identical
    multi = {n for n, m in by_name.items() if len(m) > 1}
    keep = lambda blk: [l for l in blk.splitlines() if not any(f'"{n}"' in l for n in multi)]
    assert keep(new_mis) == keep(orig_mis)                       # mismatch identical for single-MAC tenants


def test_each_file_has_its_own_template():
    office = 'class "{{ class_name }}" {\n  match if {% for p in pairs %}hardware = {{ p.mac }}{{ " or " if not loop.last }}{% endfor %};\n}\n'
    raw = [("A", ["aa:aa:aa:aa:aa:01"], None), ("B", ["aa:aa:aa:aa:aa:02"], "10.0.0.2")]
    assert build_file("Office", raw, office).text == 'class "Office" {\n  match if hardware = AA:AA:AA:AA:AA:01;\n}\n'
    assert build_file("Office", raw, "{% for h in hosts %}{{ h.host }}={{ h.ip }}\n{% endfor %}").text == "B=10.0.0.2\n"
