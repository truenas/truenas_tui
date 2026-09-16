"""Unit tests for pure/near-pure helpers in plugins/network_interface/view.py."""

from unittest.mock import MagicMock, patch

import pytest

from truenas_tui.api_methods import Method
from truenas_tui.plugins.network_interface.view import (
    NetworkInterfacePlugin,
    _alias_str,
    _iface_summary,
    _parse_alias_entry,
    _validate_alias_str,
    _validate_ip_only,
    _parse_ip_only,
    _choice_idx,
    _aliases_to_payload,
    _collect_payload,
)


def test_alias_str_with_netmask():
    alias = {"address": "192.168.1.1", "netmask": 24}
    assert _alias_str(alias) == "192.168.1.1/24"


def test_alias_str_with_prefix_length():
    alias = {"address": "10.0.0.1", "prefix_length": 8}
    assert _alias_str(alias) == "10.0.0.1/8"


def test_alias_str_no_prefix():
    alias = {"address": "192.168.1.1"}
    assert _alias_str(alias) == "192.168.1.1"


def test_summary_basic():
    iface = {
        "name": "eno1",
        "type": "PHYSICAL",
        "aliases": [{"type": "INET", "address": "192.168.1.1", "netmask": 24}],
        "state": {"aliases": []},
    }
    result = _iface_summary(iface)
    assert "eno1" in result
    assert "192.168.1.1/24" in result


def test_summary_no_addresses():
    iface = {
        "name": "eno2",
        "type": "PHYSICAL",
        "aliases": [],
        "state": {"aliases": []},
    }
    result = _iface_summary(iface)
    assert "eno2" in result
    assert "no addresses" in result


def test_summary_ipv6():
    iface = {
        "name": "eno3",
        "type": "PHYSICAL",
        "aliases": [{"type": "INET6", "address": "2001:db8::1", "netmask": 64}],
        "state": {"aliases": []},
    }
    result = _iface_summary(iface)
    assert "2001:db8::1/64" in result


def test_summary_state_aliases():
    iface = {
        "name": "eno4",
        "type": "PHYSICAL",
        "aliases": [],
        "state": {"aliases": [{"type": "INET", "address": "10.0.0.1", "netmask": 8}]},
    }
    result = _iface_summary(iface)
    assert "10.0.0.1/8" in result


def test_summary_non_physical_type_shown():
    iface = {
        "name": "vlan0",
        "type": "VLAN",
        "aliases": [],
        "state": {"aliases": []},
    }
    result = _iface_summary(iface)
    assert "[VLAN]" in result


def test_summary_physical_type_not_shown():
    iface = {
        "name": "eno1",
        "type": "PHYSICAL",
        "aliases": [],
        "state": {"aliases": []},
    }
    result = _iface_summary(iface)
    assert "[PHYSICAL]" not in result


def test_summary_uses_id_fallback():
    iface = {"id": "bond0", "type": "PHYSICAL", "aliases": [], "state": {"aliases": []}}
    result = _iface_summary(iface)
    assert "bond0" in result


def test_parse_alias_entry_valid_ipv4():
    alias, err = _parse_alias_entry("192.168.1.1/24")
    assert err is None
    assert alias == {"type": "INET", "address": "192.168.1.1", "netmask": 24}


def test_parse_alias_entry_valid_ipv6():
    alias, err = _parse_alias_entry("2001:db8::1/64")
    assert err is None
    assert alias["type"] == "INET6"
    assert alias["address"] == "2001:db8::1"
    assert alias["netmask"] == 64


def test_parse_alias_entry_no_slash():
    alias, err = _parse_alias_entry("192.168.1.1")
    assert alias is None
    assert err is not None


def test_parse_alias_entry_invalid_prefix():
    alias, err = _parse_alias_entry("192.168.1.1/abc")
    assert alias is None
    assert err is not None


def test_parse_alias_entry_invalid_ip():
    alias, err = _parse_alias_entry("999.999.999.999/24")
    assert alias is None
    assert err is not None


def test_parse_alias_entry_prefix_out_of_range_ipv4():
    alias, err = _parse_alias_entry("192.168.1.1/33")
    assert alias is None
    assert err is not None


def test_parse_alias_entry_prefix_out_of_range_ipv6():
    alias, err = _parse_alias_entry("2001:db8::1/129")
    assert alias is None
    assert err is not None


def test_validate_alias_str_valid():
    assert _validate_alias_str("10.0.0.1/8") is None


def test_validate_alias_str_invalid():
    err = _validate_alias_str("not-valid")
    assert err is not None
    assert isinstance(err, str)


def test_validate_ip_only_valid_ipv4():
    assert _validate_ip_only("192.168.1.1") is None


def test_validate_ip_only_valid_ipv6():
    assert _validate_ip_only("2001:db8::1") is None


def test_validate_ip_only_with_slash():
    err = _validate_ip_only("192.168.1.1/24")
    assert err is not None


def test_validate_ip_only_invalid():
    err = _validate_ip_only("not-an-ip")
    assert err is not None


def test_parse_ip_only_ipv4():
    result = _parse_ip_only("10.0.0.1")
    assert result == {"type": "INET", "address": "10.0.0.1"}


def test_parse_ip_only_ipv6():
    result = _parse_ip_only("2001:db8::1")
    assert result == {"type": "INET6", "address": "2001:db8::1"}


def test_choice_idx_found():
    assert _choice_idx(["A", "B", "C"], "B") == 1


def test_choice_idx_first():
    assert _choice_idx(["A", "B", "C"], "A") == 0


def test_choice_idx_missing():
    assert _choice_idx(["A", "B", "C"], "X") == 0


def test_choice_idx_empty_list():
    assert _choice_idx([], "A") == 0


def test_aliases_to_payload_empty():
    assert _aliases_to_payload([]) == []


def test_aliases_to_payload_valid():
    result = _aliases_to_payload(["192.168.1.1/24", "10.0.0.1/8"])
    assert len(result) == 2
    assert result[0] == {"type": "INET", "address": "192.168.1.1", "netmask": 24}


def test_aliases_to_payload_invalid():
    result = _aliases_to_payload(["192.168.1.1"])  # no slash
    assert isinstance(result, str)  # error string


def _make_basic_result(**overrides):
    base = {
        "description": "test iface",
        "ipv4_dhcp": False,
        "ipv6_auto": False,
        "_aliases": [],
        "mtu": 0,
    }
    base.update(overrides)
    return base


def test_collect_basic_fields():
    result = _make_basic_result(description="My Interface")
    payload = _collect_payload(result, {"type": "PHYSICAL"}, False, False)
    assert isinstance(payload, dict)
    assert payload["description"] == "My Interface"
    assert payload["ipv4_dhcp"] is False
    assert payload["ipv6_auto"] is False
    assert payload["aliases"] == []


def test_collect_mtu_zero():
    result = _make_basic_result(mtu=0)
    payload = _collect_payload(result, {"type": "PHYSICAL"}, False, False)
    assert payload["mtu"] is None  # 0 → None (use system default)


def test_collect_mtu_nonzero():
    result = _make_basic_result(mtu=9000)
    payload = _collect_payload(result, {"type": "PHYSICAL"}, False, False)
    assert payload["mtu"] == 9000


def test_collect_dhcp_mode():
    result = _make_basic_result(ipv4_dhcp=True, ipv6_auto=True)
    payload = _collect_payload(result, {"type": "PHYSICAL"}, False, False)
    assert payload["ipv4_dhcp"] is True
    assert payload["ipv6_auto"] is True


def test_collect_alias_parse_error():
    result = _make_basic_result(_aliases=["bad-no-slash"])
    payload = _collect_payload(result, {"type": "PHYSICAL"}, False, False)
    assert isinstance(payload, str)  # error string returned


def test_collect_vlan():
    result = {
        "description": "",
        "_aliases": [],
        "vlan_parent_interface": "eno1",
        "vlan_tag": 100,
        "vlan_pcp": 2,
        "mtu": 1500,
    }
    payload = _collect_payload(result, {"type": "VLAN"}, False, False)
    assert isinstance(payload, dict)
    assert payload["vlan_parent_interface"] == "eno1"
    assert payload["vlan_tag"] == 100
    assert payload["vlan_pcp"] == 2
    assert payload["mtu"] == 1500


def test_collect_bridge():
    result = {
        "description": "",
        "_aliases": [],
        "bridge_members": ["eno1", "eno2"],
        "mtu": 0,
    }
    payload = _collect_payload(result, {"type": "BRIDGE"}, False, False)
    assert isinstance(payload, dict)
    assert payload["bridge_members"] == ["eno1", "eno2"]


def test_collect_lag():
    result = {
        "description": "",
        "_aliases": [],
        "lag_protocol": "LACP",
        "lag_ports": ["eno1", "eno2"],
        "xmit_hash_policy": "LAYER2+3",
        "lacpdu_rate": "SLOW",
        "mtu": 0,
    }
    payload = _collect_payload(result, {"type": "LINK_AGGREGATION"}, False, False)
    assert isinstance(payload, dict)
    assert payload["lag_protocol"] == "LACP"
    assert payload["lag_ports"] == ["eno1", "eno2"]
    assert payload["xmit_hash_policy"] == "LAYER2+3"
    assert payload["lacpdu_rate"] == "SLOW"


def test_collect_failover_licensed():
    result = {
        "description": "",
        "_aliases": [],
        "failover_critical": True,
        "failover_group": 2,
        "_failover_aliases": ["10.0.0.1"],
        "_failover_virtual_aliases": ["10.0.0.254"],
        "mtu": 0,
    }
    payload = _collect_payload(
        result, {"type": "PHYSICAL"}, failover_licensed=True, is_create=False
    )
    assert isinstance(payload, dict)
    # DHCP must be False when HA licensed
    assert payload["ipv4_dhcp"] is False
    assert payload["ipv6_auto"] is False
    assert payload["failover_critical"] is True
    assert payload["failover_group"] == 2
    assert payload["failover_aliases"] == [{"type": "INET", "address": "10.0.0.1"}]
    assert payload["failover_virtual_aliases"] == [
        {"type": "INET", "address": "10.0.0.254"}
    ]


def test_collect_failover_invalid_ip():
    result = {
        "description": "",
        "_aliases": [],
        "failover_critical": False,
        "failover_group": 1,
        "_failover_aliases": ["not-an-ip"],
        "_failover_virtual_aliases": [],
        "mtu": 0,
    }
    payload = _collect_payload(
        result, {"type": "PHYSICAL"}, failover_licensed=True, is_create=False
    )
    assert isinstance(payload, str)  # error string


def _make_plugin_and_stdscr():
    plugin = NetworkInterfacePlugin()
    stdscr = MagicMock()
    stdscr.getmaxyx.return_value = (24, 80)
    return plugin, stdscr


def test_get_status_waiting():
    plugin, _ = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.return_value = 45  # 45 seconds remaining
    status = plugin._get_status(session)
    assert "45" in status
    assert (
        "persist" in status.lower()
        or "roll" in status.lower()
        or "p]" in status.lower()
    )


def test_get_status_pending():
    plugin, _ = _make_plugin_and_stdscr()
    session = MagicMock()
    # First call (checkin_waiting) returns None, second (has_pending_changes) returns True
    session.call.side_effect = [None, True]
    status = plugin._get_status(session)
    assert status != ""
    assert "pending" in status.lower() or "[a]" in status.lower()


def test_get_status_idle():
    plugin, _ = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.side_effect = [None, False]
    status = plugin._get_status(session)
    assert status == ""


def test_get_status_exception():
    plugin, _ = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.side_effect = Exception("API error")
    status = plugin._get_status(session)
    assert status == ""


def test_apply_changes_success():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.return_value = None  # commit succeeds

    with patch("truenas_tui.plugins.network_interface.view.message_dialog") as mock_msg:
        plugin._apply_changes(stdscr, session)

    session.call.assert_called_once_with(Method.INTERFACE_COMMIT)
    mock_msg.assert_called_once()
    # Should show a success dialog (not 'Error')
    call_args = mock_msg.call_args[0]
    assert call_args[1] != "Error"


def test_apply_changes_exception():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.side_effect = Exception("commit failed")

    with patch("truenas_tui.plugins.network_interface.view.message_dialog") as mock_msg:
        plugin._apply_changes(stdscr, session)

    mock_msg.assert_called_once()


def test_persist_changes_success():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.return_value = None

    with patch("truenas_tui.plugins.network_interface.view.message_dialog") as mock_msg:
        plugin._persist_changes(stdscr, session)

    session.call.assert_called_once_with(Method.INTERFACE_CHECKIN)
    mock_msg.assert_called_once()


def test_persist_changes_exception():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.side_effect = Exception("checkin failed")

    with patch("truenas_tui.plugins.network_interface.view.message_dialog") as mock_msg:
        plugin._persist_changes(stdscr, session)

    mock_msg.assert_called_once()


def test_delete_confirmed():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    iface = {"id": "vlan0", "name": "vlan0"}

    with (
        patch(
            "truenas_tui.plugins.network_interface.view.confirm_dialog",
            return_value=True,
        ),
        patch("truenas_tui.plugins.network_interface.view.message_dialog"),
    ):
        plugin._delete_interface(stdscr, session, iface)

    session.call.assert_called_once_with(Method.INTERFACE_DELETE, "vlan0")


def test_delete_cancelled():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    iface = {"id": "vlan0", "name": "vlan0"}

    with patch(
        "truenas_tui.plugins.network_interface.view.confirm_dialog", return_value=False
    ):
        plugin._delete_interface(stdscr, session, iface)

    session.call.assert_not_called()


def test_delete_api_exception():
    plugin, stdscr = _make_plugin_and_stdscr()
    session = MagicMock()
    session.call.side_effect = Exception("permission denied")
    iface = {"id": "vlan0", "name": "vlan0"}

    with (
        patch(
            "truenas_tui.plugins.network_interface.view.confirm_dialog",
            return_value=True,
        ),
        patch("truenas_tui.plugins.network_interface.view.message_dialog") as mock_msg,
    ):
        plugin._delete_interface(stdscr, session, iface)

    mock_msg.assert_called_once()
