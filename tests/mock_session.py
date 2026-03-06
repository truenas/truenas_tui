"""
Fake session with hardcoded responses — no network connection required.
Used by run_mock_tui.py so we can test TUI behaviour with pexpect.
"""
from truenas_tui.api_methods import Method
from truenas_tui.tui_preferences import TuiPreferences


class MockConfig:
    server = '192.168.1.108'
    username = 'admin'
    api_key_path = None

    def get_api_key(self):
        return None


_FAKE_INTERFACES = [
    {
        'id': 'eno1', 'name': 'eno1', 'type': 'PHYSICAL',
        'ipv4_dhcp': False, 'ipv6_auto': False,
        'aliases': [{'type': 'INET', 'address': '192.168.1.108', 'netmask': 24}],
        'state': {'aliases': [{'type': 'INET', 'address': '192.168.1.108', 'netmask': 24}]},
    },
    {
        'id': 'eno2', 'name': 'eno2', 'type': 'PHYSICAL',
        'ipv4_dhcp': False, 'ipv6_auto': False,
        'aliases': [],
        'state': {'aliases': []},
    },
]

_FAKE_NETCFG = {
    'hostname': 'mocknas',
    'domain': 'test.local',
    'ipv4gateway': '192.168.1.1',
    'ipv6gateway': '',
    'nameserver1': '8.8.8.8',
    'nameserver2': '',
    'nameserver3': '',
}

_FAKE_ME = {
    'pw_name': 'admin',
    'pw_gecos': 'Administrator',
    'pw_dir': '/root',
    'pw_shell': '/usr/bin/cli_console',
    'pw_uid': 0,
    'pw_gid': 0,
    'source': 'LOCAL',
    'local': True,
    'account_attributes': ['LOCAL'],
    'privilege': {
        'roles': {
            'FULL_ADMIN',
            'NETWORK_INTERFACE_READ',
            'NETWORK_INTERFACE_WRITE',
            'NETWORK_GENERAL_READ',
            'NETWORK_GENERAL_WRITE',
            'ACCOUNT_READ',
            'ACCOUNT_WRITE',
        },
        'allowlist': [],
    },
    'attributes': {
        'preferences': {
            'language': 'en',
            'dateFormat': 'yyyy-MM-DD',
            'timeFormat': 'HH:mm:ss',
        },
    },
    'two_factor_config': {
        'secret_configured': False,
        'provisioning_uri': None,
        'interval': 30,
        'otp_digits': 6,
    },
}

_FAKE_SYSINFO = {
    'hostname': 'mocknas',
    'version': 'TrueNAS-SCALE-25.10.0',
    'model': 'Intel(R) Xeon(R) E-2136',
    'cores': 12,
    'physical_cores': 6,
    'physmem': 68719476736,   # 64 GiB
    'ecc_memory': True,
    'uptime': '3 days, 4:12:05',
    'uptime_seconds': 273125.0,
    'loadavg': [0.25, 0.18, 0.12],
    'system_product': 'TRUENAS-R20',
    'system_serial': 'A123456',
    'system_manufacturer': 'iXsystems',
    'timezone': 'America/New_York',
    'boottime': None,
    'license': None,
}

_FAKE_ADMINS = [
    {'id': 1, 'username': 'admin'},
]


class MockSession:
    """Drop-in replacement for Session that returns static fake data."""

    def __init__(self):
        self.config = MockConfig()
        self.me = _FAKE_ME
        self.system_info = _FAKE_SYSINFO
        self.api_version = (25, 10, 0)
        self.api_versions = [(25, 4, 0), (25, 4, 1), (25, 4, 2), (25, 10, 0)]
        self.tui_prefs = TuiPreferences()

    def connect(self):
        pass

    def close(self):
        pass

    # ------------------------------------------------------------------ #
    # Properties mirroring Session                                        #
    # ------------------------------------------------------------------ #

    @property
    def username(self):
        return self.me['pw_name']

    @property
    def roles(self):
        return self.me['privilege']['roles']

    @property
    def role_label(self):
        for label in ('FULL_ADMIN', 'SHARING_ADMIN', 'READONLY_ADMIN'):
            if label in self.roles:
                return label
        return 'CUSTOM'

    @property
    def hostname(self):
        return self.system_info['hostname']

    @property
    def version(self):
        return self.system_info['version']

    def has_role(self, *roles):
        return bool(self.roles & set(roles))

    @property
    def date_format(self) -> str:
        return self.tui_prefs.date_format

    @property
    def time_format(self) -> str:
        return self.tui_prefs.time_format

    # ------------------------------------------------------------------ #
    # Fake API call dispatcher                                            #
    # ------------------------------------------------------------------ #

    def call(self, method, *args, **kwargs):
        dispatch = {
            Method.AUTH_ME: lambda: _FAKE_ME,
            Method.SYSTEM_INFO: lambda: _FAKE_SYSINFO,
            Method.INTERFACE_QUERY: lambda: _FAKE_INTERFACES,
            Method.INTERFACE_HAS_PENDING_CHANGES: lambda: False,
            Method.INTERFACE_CHECKIN_WAITING: lambda: None,
            Method.INTERFACE_COMMIT: lambda: None,
            Method.INTERFACE_CHECKIN: lambda: None,
            Method.INTERFACE_UPDATE: lambda: _FAKE_INTERFACES[0],
            Method.NETWORK_CONFIGURATION_CONFIG: lambda: _FAKE_NETCFG,
            Method.NETWORK_CONFIGURATION_UPDATE: lambda: _FAKE_NETCFG,
            Method.STATICROUTE_QUERY: lambda: [],
            Method.STATICROUTE_CREATE: lambda: {},
            Method.STATICROUTE_UPDATE: lambda: {},
            Method.STATICROUTE_DELETE: lambda: True,
            Method.USER_HAS_LOCAL_ADMINISTRATOR_SET_UP: lambda: True,
            Method.PRIVILEGE_LOCAL_ADMINISTRATORS: lambda: _FAKE_ADMINS,
            Method.USER_UPDATE: lambda: {},
            Method.AUTH_TWOFACTOR_UPDATE: lambda: {},
            Method.USER_SETUP_LOCAL_ADMINISTRATOR: lambda: {},
            Method.AUTH_GENERATE_ONETIME_PASSWORD: lambda: 'mock-otp-abc123',
            Method.USER_SET_PASSWORD: lambda: None,
            Method.USER_RENEW_2FA_SECRET: lambda: {
                **_FAKE_ME,
                'two_factor_config': {
                    'secret_configured': True,
                    'provisioning_uri': (
                        'otpauth://totp/admin-mocknas%40TrueNAS'
                        '?secret=JBSWY3DPEBLW64TMMQ'
                        '&issuer=iXsystems&digits=6&period=30'
                    ),
                    'interval': 30,
                    'otp_digits': 6,
                },
            },
            Method.USER_UNSET_2FA_SECRET: lambda: None,
            Method.CORE_PING: lambda: 'pong',
            Method.SYSTEM_GENERAL_GET_UI_URLS: lambda: ['https://192.168.1.108'],
            Method.AUTH_SET_ATTRIBUTE: lambda: None,
            Method.SYSTEM_CONFIG_RESET: lambda: None,
            Method.SYSTEM_REBOOT: lambda: None,
            Method.SYSTEM_SHUTDOWN: lambda: None,
        }
        handler = dispatch.get(method)
        if handler:
            return handler()
        raise NotImplementedError(f'MockSession: unhandled call {method!r}')


class RecordingMockSession(MockSession):
    """
    MockSession subclass that records every .call() invocation for assertion.

    Usage::

        session = RecordingMockSession()
        # Override specific method responses as needed:
        session.override(Method.STATICROUTE_QUERY, [my_route])
        plugin.run(stdscr, session)
        assert session.was_called(Method.SYSTEM_REBOOT)
        (args, kwargs) = session.called_with(Method.SYSTEM_REBOOT)[0]
    """

    def __init__(self):
        super().__init__()
        self.calls: list[tuple] = []   # list of (method, args, kwargs)
        self._overrides: dict = {}     # method → return value override

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
