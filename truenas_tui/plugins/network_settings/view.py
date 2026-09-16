"""
Network Settings plugin.

Edits global network configuration:
  hostname, domain, IPv4/IPv6 gateways, nameservers 1-3.

API:
  network.configuration.config   → current settings (no args)
  network.configuration.update   → save changes
"""

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import format_error
from truenas_tui.tui.dialogs import message_dialog
from truenas_tui.tui.forms import Form, FormField

from .localization import TRANSLATE


class NetworkSettingsPlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"NETWORK_GENERAL_WRITE"})
    LEGACY_INDEX = 2
    DEFAULT_HIDDEN = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Configure network settings"
    DESCRIPTION = (
        "Configure global network settings:\n"
        "\n"
        "  • Hostname and domain\n"
        "  • Default IPv4 and IPv6 gateways\n"
        "  • DNS nameservers (up to three)\n"
        "\n"
        "Changes take effect immediately after saving."
    )

    def run(self, stdscr, session) -> None:
        try:
            cfg = session.call(Method.NETWORK_CONFIGURATION_CONFIG)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return

        fields = [
            FormField(
                key="hostname",
                label=TRANSLATE("Hostname"),
                value=cfg.get("hostname", ""),
            ),
            FormField(
                key="domain", label=TRANSLATE("Domain"), value=cfg.get("domain", "")
            ),
            FormField(
                key="ipv4gateway",
                label=TRANSLATE("IPv4 Gateway"),
                value=cfg.get("ipv4gateway", ""),
            ),
            FormField(
                key="ipv6gateway",
                label=TRANSLATE("IPv6 Gateway"),
                value=cfg.get("ipv6gateway", ""),
            ),
            FormField(
                key="nameserver1",
                label=TRANSLATE("Nameserver 1"),
                value=cfg.get("nameserver1", ""),
            ),
            FormField(
                key="nameserver2",
                label=TRANSLATE("Nameserver 2"),
                value=cfg.get("nameserver2", ""),
            ),
            FormField(
                key="nameserver3",
                label=TRANSLATE("Nameserver 3"),
                value=cfg.get("nameserver3", ""),
            ),
        ]

        form = Form(stdscr, TRANSLATE("Network Configuration"), fields)
        result = form.run()

        if result is None:
            return

        try:
            session.call(Method.NETWORK_CONFIGURATION_UPDATE, result)
            message_dialog(
                stdscr,
                TRANSLATE("Success"),
                TRANSLATE("Network settings updated successfully."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
