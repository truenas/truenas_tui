"""
Group 1 – Internal Logic: Network interface helper functions.

Tests _alias_str, _parse_alias_entry, and _aliases_to_payload directly,
without curses or network.
"""

import pytest

from truenas_tui.plugins.network_interface.view import (
    _alias_str,
    _parse_alias_entry,
    _aliases_to_payload,
)


class TestAliasStr:
    def test_inet_with_netmask(self):
        alias = {"type": "INET", "address": "192.168.1.1", "netmask": 24}
        assert _alias_str(alias) == "192.168.1.1/24"

    def test_inet6_with_netmask(self):
        alias = {"type": "INET6", "address": "::1", "netmask": 128}
        assert _alias_str(alias) == "::1/128"

    def test_netmask_zero(self):
        alias = {"type": "INET", "address": "0.0.0.0", "netmask": 0}
        assert _alias_str(alias) == "0.0.0.0/0"

    def test_netmask_none_omitted(self):
        alias = {"type": "INET", "address": "10.0.0.1", "netmask": None}
        assert _alias_str(alias) == "10.0.0.1"

    def test_prefix_length_key_used_as_fallback(self):
        # Some API responses use 'prefix_length' instead of 'netmask'
        alias = {"type": "INET", "address": "10.0.0.1", "prefix_length": 16}
        assert _alias_str(alias) == "10.0.0.1/16"

    def test_empty_dict(self):
        # Gracefully handles missing keys
        result = _alias_str({})
        assert "/" not in result  # no spurious slash when no netmask


class TestParseAliasEntrySuccess:
    def test_valid_ipv4(self):
        alias, err = _parse_alias_entry("192.168.1.1/24")
        assert err is None
        assert alias == {"type": "INET", "address": "192.168.1.1", "netmask": 24}

    def test_valid_ipv6(self):
        alias, err = _parse_alias_entry("::1/128")
        assert err is None
        assert alias == {"type": "INET6", "address": "::1", "netmask": 128}

    def test_full_ipv6_address(self):
        alias, err = _parse_alias_entry("2001:db8::1/64")
        assert err is None
        assert alias["type"] == "INET6"
        assert alias["netmask"] == 64

    def test_ipv4_prefix_zero(self):
        alias, err = _parse_alias_entry("0.0.0.0/0")
        assert err is None
        assert alias["netmask"] == 0

    def test_ipv4_prefix_max(self):
        alias, err = _parse_alias_entry("192.168.1.1/32")
        assert err is None
        assert alias["netmask"] == 32

    def test_ipv6_prefix_max(self):
        alias, err = _parse_alias_entry("::1/128")
        assert err is None
        assert alias["netmask"] == 128

    def test_returns_tuple_of_two(self):
        result = _parse_alias_entry("10.0.0.1/8")
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestParseAliasEntryErrors:
    def test_no_slash_returns_error(self):
        alias, err = _parse_alias_entry("192.168.1.1")
        assert alias is None
        assert isinstance(err, str)
        assert len(err) > 0

    def test_non_numeric_prefix_returns_error(self):
        alias, err = _parse_alias_entry("192.168.1.1/abc")
        assert alias is None
        assert err is not None

    def test_bad_ip_address_returns_error(self):
        alias, err = _parse_alias_entry("notanip/24")
        assert alias is None
        assert err is not None

    def test_ipv4_prefix_too_large_returns_error(self):
        alias, err = _parse_alias_entry("10.0.0.1/33")
        assert alias is None
        assert err is not None

    def test_ipv6_prefix_too_large_returns_error(self):
        alias, err = _parse_alias_entry("::1/129")
        assert alias is None
        assert err is not None

    def test_negative_prefix_returns_error(self):
        alias, err = _parse_alias_entry("10.0.0.1/-1")
        assert alias is None
        assert err is not None

    def test_empty_string_returns_error(self):
        alias, err = _parse_alias_entry("")
        assert alias is None
        assert err is not None


class TestAliasesToPayload:
    def test_empty_list_returns_empty(self):
        assert _aliases_to_payload([]) == []

    def test_single_ipv4(self):
        result = _aliases_to_payload(["10.0.0.1/8"])
        assert result == [{"type": "INET", "address": "10.0.0.1", "netmask": 8}]

    def test_single_ipv6(self):
        result = _aliases_to_payload(["::1/128"])
        assert result == [{"type": "INET6", "address": "::1", "netmask": 128}]

    def test_multiple_mixed(self):
        result = _aliases_to_payload(["10.0.0.1/8", "::1/128"])
        assert isinstance(result, list)
        assert len(result) == 2
        types = {a["type"] for a in result}
        assert types == {"INET", "INET6"}

    def test_bad_entry_returns_error_string(self):
        result = _aliases_to_payload(["bad"])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_error_on_second_entry_returns_string(self):
        # First entry valid, second invalid
        result = _aliases_to_payload(["10.0.0.1/8", "bad"])
        assert isinstance(result, str)

    def test_all_valid_entries_returns_list(self):
        entries = ["10.0.0.1/8", "192.168.1.1/24", "172.16.0.1/12"]
        result = _aliases_to_payload(entries)
        assert isinstance(result, list)
        assert len(result) == 3
