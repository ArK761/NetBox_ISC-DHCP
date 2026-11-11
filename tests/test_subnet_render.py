import pytest
from netbox_isc_dhcp.subnet_render import context, default_pool_template, render_subnet, structure_errors, validate


def test_helpers_never_return_network_or_broadcast():
    c = context("10.20.3.16/28")
    assert (c["first_usable"], c["last_usable"], c["ip"](11), c["ip"](-2)) == ("10.20.3.17", "10.20.3.30", "10.20.3.27", "10.20.3.29")


def test_default_template_renders_and_validates():
    text, errors = render_subnet(default_pool_template(), "10.20.0.0/24", ["10.0.0.10", "10.0.0.20"])
    assert errors == [] and "range 10.20.0.10 10.20.0.253;" in text and "domain-name-servers 10.0.0.10, 10.0.0.20;" in text


def test_template_for_24_used_on_28_is_blocked():
    tpl = "subnet {{ network }} netmask {{ netmask }} {\n pool { range {{ ip(11) }} {{ ip(239) }}; }\n}\n"
    text, errors = render_subnet(tpl, "10.20.3.16/28")
    assert text == "" and errors and "outside" in errors[0]


def test_fixed_ranges_outside_or_overlapping_are_reported():
    assert validate("range 10.0.0.5 10.0.0.300;", "10.0.0.0/24")  # invalid ip is not matched -> no crash
    assert validate("range 10.0.1.5 10.0.1.9;", "10.0.0.0/24")
    assert validate("range 10.0.0.5 10.0.0.9;\nrange 10.0.0.8 10.0.0.20;", "10.0.0.0/24")
    assert validate("range 10.0.0.9 10.0.0.5;", "10.0.0.0/24")
    assert structure_errors("subnet 10.0.0.0 netmask 255.255.255.0 {", "10.0.0.0/24")
    assert validate("range 10.0.0.5 10.0.0.9;\nrange 10.0.0.10 10.0.0.20;", "10.0.0.0/24") == []


def test_gateway_is_global_first_or_last_usable():
    assert context("10.20.3.16/28")["gateway"] == "10.20.3.17"
    assert context("10.20.3.16/28", gateway_mode="last")["gateway"] == "10.20.3.30"
    text, errors = render_subnet(default_pool_template(), "10.20.0.0/24")
    assert "option routers 10.20.0.1;" in text and errors == []


def test_gateway_inside_a_range_is_an_error():
    tpl = "subnet {{ network }} netmask {{ netmask }} {\n option routers {{ gateway }};\n pool { range {{ ip(1) }} {{ ip(20) }}; }\n}\n"
    assert any("gateway" in e for e in render_subnet(tpl, "10.20.0.0/24")[1])


from netbox_isc_dhcp.subnet_render import structure_errors

GOOD = """## comment { not a block }
subnet 10.20.0.0 netmask 255.255.255.0 {
    default-lease-time 600;
    option routers 10.20.0.1;
    option domain-name-servers 10.0.0.1,10.0.0.2;
    deny duplicates;
    pool {
        range 10.20.0.10 10.20.0.100;
        default-lease-time 300;
        deny members of "A";
        deny members of "B";
        log (info, concat ("X ## ", host-decl-name, " ## ", binary-to-ascii (10, 8, ".", leased-address)));
    }
}
"""


def test_good_file_has_no_errors():
    assert structure_errors(GOOD, "10.20.0.0/24") == []


def test_owner_case_option_outside_subnet_and_twice():
    bad = "option domain-name-servers 1.1.1.1;\n" + GOOD.replace("    deny duplicates;", "    deny duplicates;\n    option domain-name-servers 8.8.8.8;") + "option domain-name-servers 1.1.1.1;\n"
    e = structure_errors(bad, "10.20.0.0/24")
    assert sum("outside the subnet block" in x for x in e) == 2 and any("set twice" in x for x in e)


def test_missing_semicolon_quote_paren_brace_and_wrong_subnet():
    assert any("missing ';'" in x for x in structure_errors(GOOD.replace("deny duplicates;", "deny duplicates"), "10.20.0.0/24"))
    assert any("quote" in x for x in structure_errors(GOOD.replace('"A";', '"A;'), "10.20.0.0/24"))
    assert any("parenthes" in x for x in structure_errors(GOOD.replace("leased-address)));", "leased-address));"), "10.20.0.0/24"))
    assert any("closing brace" in x for x in structure_errors(GOOD.rstrip().rstrip("}"), "10.20.0.0/24"))
    assert any("subnet must be" in x for x in structure_errors(GOOD, "10.30.0.0/24"))


SITE = {"options": {"wpad"}, "vars": {"foo"}, "classes": set()}
CLASSES = {"A", "B"}


def errs(snippet, prefix="10.20.0.0/24"):
    return structure_errors(GOOD.replace("    deny duplicates;", "    deny duplicates;\n" + snippet), prefix, SITE, CLASSES)


def test_good_file_with_site_context():
    assert structure_errors(GOOD, "10.20.0.0/24", SITE, CLASSES) == []


@pytest.mark.parametrize("line,expect", [
    ("    optin routers 10.20.0.1;", "unknown statement 'optin'"),
    ("    default-lease-tim 600;", "unknown statement 'default-lease-tim'"),
    ("    option dns-servers 1.1.1.1;", "unknown option 'dns-servers'"),
    ("    option ntp-servers 1.1.1.999;", "not an IPv4 address or host name"),
    ("    option interface-mtu big;", "not a number"),
    ("    option domain-name firma.local;", "text in quotes"),
    ("    option subnet-mask 255.255.0.0;", "differs from the subnet mask"),
    ("    max-lease-time 100;", "greater than max-lease-time"),
    ('    allow members of "Nope";', 'class "Nope" is not defined'),
    ('    log (info, concat("X ", fooo, binary-to-asci(10, 8, ".", leased-address)));', "unknown word(s) binary-to-asci, fooo"),
    ("    filename pxelinux.0;", "text in quotes"),
])
def test_deep_checks(line, expect):
    assert any(expect in e for e in errs(line)), errs(line)


def test_custom_option_and_set_variable_from_static_part_are_accepted():
    assert errs('    option wpad "http://x/wpad.dat";\n    log (info, concat("MAC ", foo));') == []


def test_routers_outside_subnet():
    bad = GOOD.replace("option routers 10.20.0.1;", "option routers 10.30.0.1;")
    assert any("not a usable address" in e for e in structure_errors(bad, "10.20.0.0/24", SITE, CLASSES))


def test_lenient_mode_ignores_site_references_but_not_size_errors():
    tpl = GOOD.replace('deny members of "A";', 'deny members of "Unknown";').replace("concat (", "concat (fooo, ")
    assert structure_errors(tpl, "10.20.0.0/24", SITE, CLASSES)            # strict: class + word errors
    assert structure_errors(tpl, "10.20.0.0/24", SITE, CLASSES, lenient=True) == []


def test_every_check_message_has_a_slovak_translation(monkeypatch):
    import netbox_isc_dhcp.i18n as i18n

    monkeypatch.setattr(i18n, "current_language", lambda: "sk")
    msgs = []
    for line, _ in [(l, e) for l, e in [
        ("    optin routers 10.20.0.1;", 0), ("    option dns-servers 1.1.1.1;", 0), ("    option ntp-servers 1.1.1.999;", 0),
        ("    option interface-mtu big;", 0), ("    option domain-name firma.local;", 0), ("    option subnet-mask 255.255.0.0;", 0),
        ("    max-lease-time 100;", 0), ('    allow members of "Nope";', 0), ('    log (info, concat("X ", fooo));', 0),
        ("    filename pxelinux.0;", 0), ("    deny duplicates", 0), ("option routers 1.1.1.1;", 0)]]:
        msgs += errs(line)
    msgs += ["size /28 is outside the range /24-/24 of the pool", "the pool code has errors", "USE X: unknown variable"]
    untranslated = [m for m in msgs if i18n.tmsg(m) == m]
    assert untranslated == []
