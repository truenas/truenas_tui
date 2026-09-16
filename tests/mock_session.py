"""
Fake session with hardcoded responses — no network connection required.
Used by run_mock_tui.py so we can test TUI behaviour with pexpect.
"""

from truenas_tui.tui_preferences import TuiPreferences


class MockConfig:
    server = "192.168.1.108"
    username = "admin"
    api_key_path = None

    def get_api_key(self):
        return None


_FAKE_INTERFACES = [
    {
        "id": "eno1",
        "name": "eno1",
        "type": "PHYSICAL",
        "ipv4_dhcp": False,
        "ipv6_auto": False,
        "aliases": [{"type": "INET", "address": "192.168.1.108", "netmask": 24}],
        "state": {
            "aliases": [{"type": "INET", "address": "192.168.1.108", "netmask": 24}]
        },
    },
    {
        "id": "eno2",
        "name": "eno2",
        "type": "PHYSICAL",
        "ipv4_dhcp": False,
        "ipv6_auto": False,
        "aliases": [],
        "state": {"aliases": []},
    },
]

_FAKE_NETCFG = {
    "hostname": "mocknas",
    "domain": "test.local",
    "ipv4gateway": "192.168.1.1",
    "ipv6gateway": "",
    "nameserver1": "8.8.8.8",
    "nameserver2": "",
    "nameserver3": "",
}

_FAKE_ME = {
    "pw_name": "admin",
    "pw_gecos": "Administrator",
    "pw_dir": "/root",
    "pw_shell": "/usr/bin/cli_console",
    "pw_uid": 0,
    "pw_gid": 0,
    "source": "LOCAL",
    "local": True,
    "account_attributes": ["LOCAL"],
    "privilege": {
        "roles": {
            "FULL_ADMIN",
            "NETWORK_INTERFACE_READ",
            "NETWORK_INTERFACE_WRITE",
            "NETWORK_GENERAL_READ",
            "NETWORK_GENERAL_WRITE",
            "ACCOUNT_READ",
            "ACCOUNT_WRITE",
        },
        "allowlist": [],
    },
    "attributes": {
        "preferences": {
            "language": "en",
            "dateFormat": "yyyy-MM-DD",
            "timeFormat": "HH:mm:ss",
        },
    },
    "two_factor_config": {
        "secret_configured": False,
        "provisioning_uri": None,
        "interval": 30,
        "otp_digits": 6,
    },
}

_FAKE_SYSINFO = {
    "hostname": "mocknas",
    "version": "TrueNAS-SCALE-25.10.0",
    "model": "Intel(R) Xeon(R) E-2136",
    "cores": 12,
    "physical_cores": 6,
    "physmem": 68719476736,  # 64 GiB
    "ecc_memory": True,
    "uptime": "3 days, 4:12:05",
    "uptime_seconds": 273125.0,
    "loadavg": [0.25, 0.18, 0.12],
    "system_product": "TRUENAS-R20",
    "system_serial": "A123456",
    "system_manufacturer": "iXsystems",
    "timezone": "America/New_York",
    "boottime": None,
    "license": None,
}

_FAKE_ADMINS = [
    {"id": 1, "username": "admin"},
]


class MockSession:
    """Drop-in replacement for Session that returns static fake data."""

    def __init__(self):
        self.config = MockConfig()
        self.me = _FAKE_ME
        self.system_info = _FAKE_SYSINFO
        self.tui_prefs = TuiPreferences()

    def connect(self):
        pass

    def close(self):
        pass

    @property
    def username(self):
        return self.me["pw_name"]

    @property
    def roles(self):
        return self.me["privilege"]["roles"]

    @property
    def role_label(self):
        for label in ("FULL_ADMIN", "SHARING_ADMIN", "READONLY_ADMIN"):
            if label in self.roles:
                return label
        return "CUSTOM"

    @property
    def hostname(self):
        return self.system_info["hostname"]

    @property
    def version(self):
        return self.system_info["version"]

    def call(self, method, *args, **kwargs):
        dispatch = {
            "auth.me": lambda: _FAKE_ME,
            "system.info": lambda: _FAKE_SYSINFO,
            "interface.query": lambda: _FAKE_INTERFACES,
            "interface.has_pending_changes": lambda: False,
            "interface.checkin_waiting": lambda: None,
            "interface.commit": lambda: None,
            "interface.checkin": lambda: None,
            "interface.update": lambda: _FAKE_INTERFACES[0],
            "network.configuration.config": lambda: _FAKE_NETCFG,
            "network.configuration.update": lambda: _FAKE_NETCFG,
            "staticroute.query": lambda: [],
            "staticroute.create": lambda: {},
            "staticroute.update": lambda: {},
            "staticroute.delete": lambda: True,
            "user.has_local_administrator_set_up": lambda: True,
            "privilege.local_administrators": lambda: _FAKE_ADMINS,
            "user.update": lambda: {},
            "auth.twofactor.update": lambda: {},
            "user.setup_local_administrator": lambda: {},
            "auth.generate_onetime_password": lambda: "mock-otp-abc123",
            "user.set_password": lambda: None,
            "user.renew_2fa_secret": lambda: {
                **_FAKE_ME,
                "two_factor_config": {
                    "secret_configured": True,
                    "provisioning_uri": (
                        "otpauth://totp/admin-mocknas%40TrueNAS"
                        "?secret=JBSWY3DPEBLW64TMMQ"
                        "&issuer=iXsystems&digits=6&period=30"
                    ),
                    "interval": 30,
                    "otp_digits": 6,
                },
            },
            "user.unset_2fa_secret": lambda: None,
            "core.ping": lambda: "pong",
            "system.general.get_ui_urls": lambda: ["https://192.168.1.108"],
            "auth.set_attribute": lambda: None,
            "system.config.reset": lambda: None,
            "system.reboot": lambda: None,
            "system.shutdown": lambda: None,
        }
        handler = dispatch.get(method)
        if handler:
            return handler()
        raise NotImplementedError(f"MockSession: unhandled call {method!r}")


class RecordingMockSession(MockSession):
    """
    MockSession subclass that records every .call() invocation for assertion.

    Usage::

        session = RecordingMockSession()
        # Override specific method responses as needed:
        session.override("staticroute.query", [my_route])
        plugin.run(stdscr, session)
        assert session.was_called("system.reboot")
        (args, kwargs) = session.called_with("system.reboot")[0]
    """

    def __init__(self):
        super().__init__()
        self.calls: list[tuple] = []  # list of (method, args, kwargs)
        self._overrides: dict = {}  # method → return value override

    def override(self, method, value):
        """Pin a specific return value for one method. Returns self for chaining."""
        self._overrides[method] = value
        return self

    def call(self, method, *args, **kwargs):
        self.calls.append((method, args, kwargs))
        if method in self._overrides:
            return self._overrides[method]
        return super().call(method, *args, **kwargs)

    def called_with(self, method) -> list[tuple]:
        """Return list of (args, kwargs) tuples for every call to method."""
        return [(a, kw) for (m, a, kw) in self.calls if m == method]

    def was_called(self, method) -> bool:
        """Return True if method was called at least once."""
        return any(m == method for m, _, _ in self.calls)
