from netbox_isc_dhcp.subnet_render import context, default_pool_template, render_subnet, validate


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
    assert validate("subnet x {", "10.0.0.0/24")
    assert validate("range 10.0.0.5 10.0.0.9;\nrange 10.0.0.10 10.0.0.20;", "10.0.0.0/24") == []
