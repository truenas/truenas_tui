"""
Group 1 – Internal Logic: Config parsing.

Tests the Config class in truenas_tui.config without network or curses.
All tests use tmp_path (pytest built-in) to create real temp config files.
"""

from truenas_tui.config import Config


def _conf(tmp_path, body: str) -> str:
    """Write an INI config file to tmp_path and return its path."""
    p = tmp_path / "truenas_tui.conf"
    p.write_text(body)
    return str(p)


def test_missing_file_server_is_none(tmp_path):
    c = Config(str(tmp_path / "nonexistent.conf"))
    assert c.server is None


def test_empty_file_server_is_none(tmp_path):
    p = _conf(tmp_path, "")
    assert Config(p).server is None


def test_section_no_server_key_is_none(tmp_path):
    p = _conf(tmp_path, "[truenas]\nusername = bob\n")
    assert Config(p).server is None


def test_server_empty_value_is_none(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = \n")
    assert Config(p).server is None


def test_server_ipv4(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = 192.168.1.1\n")
    assert Config(p).server == "192.168.1.1"


def test_server_hostname(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = my-nas.local\n")
    assert Config(p).server == "my-nas.local"


def test_server_bare_hostname(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = truenas\n")
    assert Config(p).server == "truenas"


def test_server_fqdn(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = nas.example.com\n")
    assert Config(p).server == "nas.example.com"


def test_server_ipv4_with_port(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = 192.168.1.1:8080\n")
    assert Config(p).server == "192.168.1.1:8080"


def test_server_hostname_with_port(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = my-nas:443\n")
    assert Config(p).server == "my-nas:443"


def test_server_ipv6_bracketed(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = [::1]\n")
    assert Config(p).server == "[::1]"


def test_server_ipv6_bracketed_with_port(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = [::1]:8443\n")
    assert Config(p).server == "[::1]:8443"


def test_verify_ssl_default_true(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = 1.2.3.4\n")
    assert Config(p).verify_ssl is True


def test_verify_ssl_missing_key_defaults_true(tmp_path):
    p = _conf(tmp_path, "[truenas]\n")
    assert Config(p).verify_ssl is True


def test_verify_ssl_explicit_false(tmp_path):
    p = _conf(tmp_path, "[truenas]\nverify_ssl = false\n")
    assert Config(p).verify_ssl is False


def test_verify_ssl_explicit_true(tmp_path):
    p = _conf(tmp_path, "[truenas]\nverify_ssl = true\n")
    assert Config(p).verify_ssl is True


def test_verify_ssl_0_is_false(tmp_path):
    p = _conf(tmp_path, "[truenas]\nverify_ssl = 0\n")
    assert Config(p).verify_ssl is False


def test_username_returns_value(tmp_path):
    p = _conf(tmp_path, "[truenas]\nusername = bob\n")
    assert Config(p).username == "bob"


def test_username_missing_is_none(tmp_path):
    p = _conf(tmp_path, "[truenas]\nserver = 1.2.3.4\n")
    assert Config(p).username is None


def test_api_key_path_returns_value(tmp_path):
    p = _conf(tmp_path, "[truenas]\napi_key_path = /some/path.key\n")
    assert Config(p).api_key_path == "/some/path.key"


def test_api_key_path_missing_is_none(tmp_path):
    p = _conf(tmp_path, "[truenas]\n")
    assert Config(p).api_key_path is None


def test_get_api_key_no_path_returns_none(tmp_path):
    p = _conf(tmp_path, "[truenas]\n")
    assert Config(p).get_api_key() is None


def test_get_api_key_reads_file_content(tmp_path):
    key_file = tmp_path / "api.key"
    key_file.write_text("my-secret-key\n")
    key_file.chmod(0o600)
    p = _conf(tmp_path, f"[truenas]\napi_key_path = {key_file}\n")
    assert Config(p).get_api_key() == "my-secret-key"


def test_get_api_key_strips_surrounding_whitespace(tmp_path):
    key_file = tmp_path / "api.key"
    key_file.write_text("  secret-key  \n\n")
    key_file.chmod(0o600)
    p = _conf(tmp_path, f"[truenas]\napi_key_path = {key_file}\n")
    assert Config(p).get_api_key() == "secret-key"
