import configparser
import os
import re
import stat
import sys

DEFAULT_CONFIG_PATH = os.path.expanduser('~/.config/truenas_tui.conf')

# Valid server address: hostname, FQDN, IPv4, or bracketed IPv6, with optional port.
_HOST_RE = re.compile(
    r'^(?:'
    r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*'
    r'[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?'  # hostname/FQDN
    r'|\d{1,3}(?:\.\d{1,3}){3}'                          # bare IPv4
    r'|\[[\da-fA-F:]+\]'                                  # bracketed IPv6
    r')(?::\d{1,5})?$'                                    # optional :port
)


class Config:
    """
    Reads TUI configuration from an INI-style config file.

    Expected format::

        [truenas]
        server = 192.168.1.108      ; omit for AF_UNIX local connection
        username = admin
        api_key_path = /path/to/api.key
        verify_ssl = true           ; set false only for self-signed certificates
        ca_cert =                   ; optional path to a CA bundle (PEM)
    """

    def __init__(self, path=None):
        self.path = path or DEFAULT_CONFIG_PATH
        self._parser = configparser.ConfigParser()
        self._parser.read(self.path)

    @property
    def server(self):
        """Remote server address (validated), or None for local AF_UNIX."""
        raw = self._parser.get('truenas', 'server', fallback=None) or None
        if raw is not None and not _HOST_RE.match(raw):
            raise ValueError(
                f'Invalid server address in config: {raw!r}  '
                f'(expected hostname, IPv4, or [IPv6], optionally with :port)'
            )
        return raw

    @property
    def username(self):
        return self._parser.get('truenas', 'username', fallback=None)

    @property
    def api_key_path(self):
        return self._parser.get('truenas', 'api_key_path', fallback=None)

    @property
    def verify_ssl(self) -> bool:
        """Whether to verify the server's TLS certificate.

        Defaults to True.  Set to false in the config file only when
        connecting to a server with a self-signed certificate and no
        local CA bundle is available.
        """
        return self._parser.getboolean('truenas', 'verify_ssl', fallback=True)

    @property
    def ca_cert(self):
        """Optional path to a PEM CA bundle for TLS verification."""
        return self._parser.get('truenas', 'ca_cert', fallback=None) or None

    def get_api_key(self):
        """Return raw API key string from api_key_path file, or None."""
        path = self.api_key_path
        if not path:
            return None
        self._check_key_permissions(path)
        with open(path) as f:
            return f.read().strip()

    @staticmethod
    def _check_key_permissions(path: str) -> None:
        """Warn if the key file is readable by group or others."""
        try:
            mode = os.stat(path).st_mode
        except OSError:
            return  # will surface as FileNotFoundError on open()
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            print(
                f'WARNING: API key file {path!r} has loose permissions '
                f'(mode {oct(stat.S_IMODE(mode))}).  '
                f'It should be readable only by the owner (chmod 0600).',
                file=sys.stderr,
            )
