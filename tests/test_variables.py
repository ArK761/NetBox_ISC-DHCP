import pytest

from netbox_isc_dhcp.variables import VariableError, build_lines, expand_use, used_names


def test_lease_with_max_factor():
    assert build_lines("lease", "100") == "default-lease-time 100;\nmax-lease-time 130;"
    assert build_lines("lease", "600", lease_factor=1.5) == "default-lease-time 600;\nmax-lease-time 900;"


def test_dns_and_texts():
    assert build_lines("domain-name-servers", "", ["1.1.1.1", "8.8.8.8"]) == "option domain-name-servers 1.1.1.1, 8.8.8.8;"
    assert build_lines("domain-search", "a.local, b.local") == 'option domain-search "a.local", "b.local";'
    assert build_lines("unknown-clients", "deny") == "deny unknown-clients;"
    assert build_lines("raw", "deny duplicates;\nping-check true;") == "deny duplicates;\nping-check true;"


@pytest.mark.parametrize("opt,val", [("lease", "x"), ("lease", "0"), ("next-server", "1.2.3"), ("domain-name", 'a"b'),
                                     ("unknown-clients", "maybe"), ("ntp-servers", "1.1.1.1, nope"), ("domain-name-servers", "")])
def test_invalid_values(opt, val):
    with pytest.raises(VariableError):
        build_lines(opt, val)


def test_expand_use_keeps_indent_and_reports_unknown():
    tpl = "subnet x {\n        USE LEASE_SHORT\n    USE AltDNS\n  USE Nope\n}\n"
    out, err = expand_use(tpl, {"LEASE_SHORT": "default-lease-time 100;\nmax-lease-time 130;", "AltDNS": "option domain-name-servers 1.1.1.1;"})
    assert "        default-lease-time 100;\n        max-lease-time 130;\n    option domain-name-servers 1.1.1.1;\n  USE Nope" in out
    assert err == ["USE Nope: unknown variable"]
    assert used_names(tpl) == {"LEASE_SHORT", "AltDNS", "Nope"}


def test_crlf_from_browser_is_handled():
    tpl = "subnet x {\r\n  USE A\r\n}\r\n"
    out, err = expand_use(tpl, {"A": "deny duplicates;"})
    assert out == "subnet x {\n  deny duplicates;\n}\n" and err == [] and used_names(tpl) == {"A"}


def test_rename_use_lines_only_exact_name():
    from netbox_isc_dhcp.variables import rename_use

    tpl = "subnet x {\n    USE TIME_600\n    USE TIME_6000\n  USE TIME_600  \n}\n"
    assert rename_use(tpl, "TIME_600", "LEASE_10MIN") == "subnet x {\n    USE LEASE_10MIN\n    USE TIME_6000\n  USE LEASE_10MIN\n}\n"
