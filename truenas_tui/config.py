import configparser
import os
import stat
import sys

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/truenas_tui.conf")


class Config:
    """
    Reads TUI configuration from an INI-style config file.

    Expected format::

        [truenas]
        server = 192.168.1.108      ; omit for AF_UNIX local connection
        username = admin
        api_key_path = /path/to/api.key
        verify_ssl = true           ; set false only for self-signed certificates
    """

    def __init__(self, path: str | None = None) -> None:
        self.path = path or DEFAULT_CONFIG_PATH
        self._parser = configparser.ConfigParser()
        self._parser.read(self.path)

    @property
    def server(self) -> str | None:
        """Remote server address, or None for local AF_UNIX."""
        return self._parser.get("truenas", "server", fallback=None) or None

    @property
    def username(self) -> str | None:
        return self._parser.get("truenas", "username", fallback=None)

    @property
    def api_key_path(self) -> str | None:
        return self._parser.get("truenas", "api_key_path", fallback=None)

    @property
    def verify_ssl(self) -> bool:
        """Whether to verify the server's TLS certificate.  Defaults to True."""
        return self._parser.getboolean("truenas", "verify_ssl", fallback=True)

    def get_api_key(self) -> str | None:
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
                f"WARNING: API key file {path!r} has loose permissions "
                f"(mode {oct(stat.S_IMODE(mode))}).  "
                f"It should be readable only by the owner (chmod 0600).",
                file=sys.stderr,
            )
