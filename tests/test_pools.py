import pytest

from netbox_isc_dhcp.pools import PoolLayoutError, check_static_conflicts, plan_workstation_pools


def rng(r):
    return str(r.first), str(r.last)


def test_slash24_matches_original_bash_template():
    p = plan_workstation_pools("10.20.0.0/24")
    assert rng(p.dynamic) == ("10.20.0.11", "10.20.0.239")
    assert rng(p.mismatch) == ("10.20.0.240", "10.20.0.247")
    assert rng(p.unknown) == ("10.20.0.248", "10.20.0.254")
    assert str(p.gateway) == "10.20.0.1"
    assert p.netmask == "255.255.255.0"
    assert p.three_octet == "10.20.0"


def test_slash26_scales():
    p = plan_workstation_pools("10.1.2.64/26")
    assert rng(p.dynamic) == ("10.1.2.75", "10.1.2.111")
    assert rng(p.mismatch) == ("10.1.2.112", "10.1.2.119")
    assert rng(p.unknown) == ("10.1.2.120", "10.1.2.126")


@pytest.mark.parametrize("prefix", ["10.0.0.0/28", "10.0.0.0/27", "10.0.0.0/30", "10.0.0.0/32"])
def test_small_prefix_rejected_not_generated(prefix):
    with pytest.raises(PoolLayoutError):
        plan_workstation_pools(prefix)


@pytest.mark.parametrize("prefix", ["10.0.0.5/24", "garbage", "2001:db8::/64", "10.0.0.0/8"])
def test_invalid_prefix_rejected(prefix):
    with pytest.raises(PoolLayoutError):
        plan_workstation_pools(prefix)


def test_gateway_must_be_in_prefix():
    with pytest.raises(PoolLayoutError):
        plan_workstation_pools("10.0.0.0/24", gateway="10.0.1.1")


def test_gateway_inside_pool_rejected():
    with pytest.raises(PoolLayoutError):
        plan_workstation_pools("10.0.0.0/24", gateway="10.0.0.100")


def test_static_conflicts():
    p = plan_workstation_pools("10.20.0.0/24")
    assert check_static_conflicts(p, ["10.20.0.5/24", "10.20.0.50/24", "10.20.0.250/24"]) == [
        "10.20.0.50",
        "10.20.0.250",
    ]


def test_every_supported_size_has_no_overlaps():
    for plen in range(16, 27):
        plan_workstation_pools(f"10.0.0.0/{plen}")
