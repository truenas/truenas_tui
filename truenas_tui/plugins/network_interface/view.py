"""
Network Interface plugin.

Shows a list of network interfaces with their current IP addresses.
Selecting one opens a form to edit settings (DHCP, aliases, MTU, type-specific
fields).  Supports creating and deleting interfaces.  After editing, the user
can Apply (interface.commit) and then Persist (interface.checkin) or let the
changes roll back automatically.

API:
  interface.query                          → list interfaces
  interface.create <data>                  → create a new interface
  interface.update <id> <data>             → update an interface
  interface.delete <id>                    → delete an interface
  interface.commit                         → apply pending changes (starts rollback timer)
  interface.checkin                        → persist applied changes permanently
  interface.checkin_waiting                → seconds left before rollback (or None)
  interface.has_pending_changes            → bool
  interface.bridge_members_choices <name>  → dict of valid bridge member names
  interface.lag_ports_choices <name>       → dict of valid LAG port names
  interface.vlan_parent_interface_choices  → dict of valid VLAN parent names
  failover.licensed                        → bool (HA system)

Version notes:
  No known breaking changes between supported API versions for these calls.
"""

import curses
import ipaddress

from truenas_tui.api_methods import Method
from truenas_tui.plugins.base import BasePlugin
from truenas_tui.tui import HardExit, colors, format_error
from truenas_tui.tui.colors import pair
from truenas_tui.tui.dialogs import confirm_dialog, message_dialog
from truenas_tui.tui.forms import (
    BoolField,
    ChoiceField,
    Form,
    FormField,
    IntField,
    ListField,
    SectionField,
)

from .localization import TRANSLATE

_LAG_PROTOCOLS = ["LACP", "FAILOVER", "LOADBALANCE", "ROUNDROBIN", "NONE"]
_XMIT_POLICIES = ["LAYER2", "LAYER2+3", "LAYER3+4"]
_LACPDU_RATES = ["SLOW", "FAST"]
_IFACE_TYPES = ["BRIDGE", "LINK_AGGREGATION", "VLAN"]


def _alias_str(alias: dict) -> str:
    """Format an alias dict into a human-readable CIDR string."""
    addr = alias.get("address", "")
    netmask = alias.get("netmask")
    plen = netmask if netmask is not None else alias.get("prefix_length")
    if plen is not None:
        return f"{addr}/{plen}"
    return addr


def _iface_summary(iface: dict) -> str:
    """One-line summary for the interface list."""
    name = iface.get("name", iface.get("id", "?"))
    itype = iface.get("type", "")
    aliases = iface.get("aliases", [])
    state_aliases = (iface.get("state") or {}).get("aliases", [])

    configured = [_alias_str(a) for a in aliases if a.get("type") in ("INET", "INET6")]
    active = [
        _alias_str(a) for a in state_aliases if a.get("type") in ("INET", "INET6")
    ]

    parts = []
    if itype and itype not in ("PHYSICAL",):
        parts.append(f"[{itype}]")
    if configured:
        parts.append("cfg: " + ", ".join(configured))
    if active:
        parts.append("act: " + ", ".join(active))
    suffix = "  ".join(parts) if parts else TRANSLATE("(no addresses)")
    return f"{name:<12}  {suffix}"


def _parse_alias_entry(entry: str) -> tuple[dict | None, str | None]:
    """
    Parse a single 'address/prefix' CIDR string into an alias dict.

    Returns (alias_dict, None) on success or (None, error_message) on failure.
    """
    if "/" not in entry:
        return None, TRANSLATE(
            "Alias must be in CIDR notation (e.g. 192.168.1.1/24): {e}"
        ).format(e=entry)
    addr, plen_str = entry.rsplit("/", 1)
    try:
        plen = int(plen_str)
    except ValueError:
        return None, TRANSLATE("Invalid prefix length in alias: {e}").format(e=entry)
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return None, TRANSLATE("Invalid IP address in alias: {e}").format(e=entry)
    aftype = "INET6" if isinstance(ip, ipaddress.IPv6Address) else "INET"
    max_prefix = 128 if aftype == "INET6" else 32
    if not (0 <= plen <= max_prefix):
        return None, TRANSLATE("Prefix length out of range in alias: {e}").format(
            e=entry
        )
    return {"type": aftype, "address": addr, "netmask": plen}, None


def _validate_alias_str(s: str) -> str | None:
    """Return error string or None.  Used as ListField item_validator."""
    _, err = _parse_alias_entry(s)
    return err


def _validate_ip_only(s: str) -> str | None:
    """Validate a bare IP address (no prefix length).  Used for HA failover lists."""
    if "/" in s:
        return TRANSLATE("Specify a bare IP address (no prefix length)")
    try:
        ipaddress.ip_address(s)
        return None
    except ValueError:
        return TRANSLATE("Invalid IP address: {s}").format(s=s)


def _parse_ip_only(s: str) -> dict:
    """Convert a bare IP string to a minimal alias dict (address only, no netmask)."""
    ip = ipaddress.ip_address(s)
    return {
        "type": "INET6" if isinstance(ip, ipaddress.IPv6Address) else "INET",
        "address": s,
    }


def _choice_idx(choices: list[str], value: str) -> int:
    """Return index of value in choices, or 0 if not found."""
    try:
        return choices.index(value)
    except ValueError:
        return 0


def _aliases_to_payload(alias_strings: list[str]) -> list[dict] | str:
    """
    Convert a list of CIDR strings to alias dicts for the API payload.
    Returns list[dict] on success or an error string on failure.
    """
    result = []
    for s in alias_strings:
        alias, err = _parse_alias_entry(s)
        if err:
            return err
        result.append(alias)
    return result


class NetworkInterfacePlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"NETWORK_INTERFACE_WRITE"})
    LEGACY_INDEX = 1
    DEFAULT_HIDDEN = True
    _TRANSLATE = staticmethod(TRANSLATE)
    LABEL = "Configure network interfaces"
    DESCRIPTION = (
        "View and edit network interface configuration.\n"
        "\n"
        "  • Enable/disable DHCP and IPv6 auto-configuration\n"
        "  • Add or remove static IP aliases\n"
        "  • Set MTU, VLAN tag, bridge members, LAG ports, and more\n"
        "  • Apply changes (with automatic rollback safety)\n"
        "  • Persist changes once the network is confirmed working\n"
        "\n"
        "Press Enter to select an interface to edit.\n"
        "Press [n] to create a new interface, [d] to delete.\n"
        "After editing, use [a] to Apply and [p] to Persist."
    )

    def run(self, stdscr, session) -> None:
        while True:
            action = self._list_screen(stdscr, session)
            if action is None:
                break

    def _list_screen(self, stdscr, session) -> str | None:
        try:
            ifaces = session.call(Method.INTERFACE_QUERY)
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
            return None

        status_msg = self._get_status(session)
        selected = 0
        stdscr.keypad(True)
        curses.curs_set(0)

        while True:
            self._draw_list(stdscr, ifaces, selected, status_msg)
            key = stdscr.getch()

            if key == 4:
                raise HardExit()
            elif key in (27, ord("q")):
                return None
            elif key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(max(0, len(ifaces) - 1), selected + 1)
            elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER):
                if ifaces:
                    self._edit_interface(stdscr, session, ifaces[selected])
                    try:
                        ifaces = session.call(Method.INTERFACE_QUERY)
                        selected = min(selected, max(0, len(ifaces) - 1))
                    except Exception:
                        pass
                    status_msg = self._get_status(session)
            elif key == ord("n"):
                self._create_interface(stdscr, session)
                try:
                    ifaces = session.call(Method.INTERFACE_QUERY)
                    selected = min(selected, max(0, len(ifaces) - 1))
                except Exception:
                    pass
                status_msg = self._get_status(session)
            elif key == ord("d"):
                if ifaces:
                    self._delete_interface(stdscr, session, ifaces[selected])
                    try:
                        ifaces = session.call(Method.INTERFACE_QUERY)
                        selected = min(selected, max(0, len(ifaces) - 1))
                    except Exception:
                        pass
                    status_msg = self._get_status(session)
            elif key == ord("a"):
                self._apply_changes(stdscr, session)
                status_msg = self._get_status(session)
            elif key == ord("p"):
                self._persist_changes(stdscr, session)
                status_msg = self._get_status(session)

    def _get_status(self, session) -> str:
        try:
            waiting = session.call(Method.INTERFACE_CHECKIN_WAITING)
            if waiting is not None:
                return TRANSLATE(
                    "Changes applied. Press [p] to persist or they roll back in {n}s."
                ).format(n=int(waiting))
            if session.call(Method.INTERFACE_HAS_PENDING_CHANGES):
                return TRANSLATE("Pending changes. Press [a] to apply.")
        except Exception:
            pass
        return ""

    def _draw_list(self, stdscr, ifaces: list, selected: int, status: str) -> None:
        stdscr.erase()
        sh, sw = stdscr.getmaxyx()

        title = TRANSLATE("Network Interfaces")
        stdscr.addstr(
            0, 0, f" {title} ".center(sw), pair(colors.HEADER) | curses.A_BOLD
        )

        if status:
            try:
                stdscr.addstr(
                    1, 2, status[: sw - 3], pair(colors.WARNING) | curses.A_BOLD
                )
            except curses.error:
                pass

        list_top = 2 if status else 1
        for i, iface in enumerate(ifaces):
            row = list_top + i + 1
            if row >= sh - 2:
                break
            summary = _iface_summary(iface)[: sw - 3]
            attr = (
                pair(colors.MENU_SELECTED) | curses.A_BOLD
                if i == selected
                else curses.A_NORMAL
            )
            try:
                stdscr.addstr(row, 2, f"{summary:<{sw - 4}}", attr)
            except curses.error:
                pass

        hint = TRANSLATE(
            "[↑↓] Navigate  [Enter] Edit  [n] New  [d] Delete  [a] Apply  [p] Persist  [q] Back"
        )
        try:
            stdscr.addstr(sh - 1, 0, hint[:sw], pair(colors.HEADER))
        except curses.error:
            pass

        stdscr.refresh()

    def _apply_changes(self, stdscr, session) -> None:
        try:
            session.call(Method.INTERFACE_COMMIT)
            message_dialog(
                stdscr,
                TRANSLATE("Applied"),
                TRANSLATE(
                    "Changes applied. Network will roll back in ~60 seconds\n"
                    "unless you press [p] to persist them."
                ),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _persist_changes(self, stdscr, session) -> None:
        try:
            session.call(Method.INTERFACE_CHECKIN)
            message_dialog(
                stdscr,
                TRANSLATE("Persisted"),
                TRANSLATE("Network changes persisted successfully."),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _delete_interface(self, stdscr, session, iface: dict) -> None:
        iface_id = iface.get("id") or iface.get("name")
        iface_name = iface.get("name", iface_id)
        if not confirm_dialog(
            stdscr,
            TRANSLATE("Confirm Delete"),
            TRANSLATE("Delete interface {name}?").format(name=iface_name),
        ):
            return
        try:
            session.call(Method.INTERFACE_DELETE, iface_id)
            message_dialog(
                stdscr,
                TRANSLATE("Deleted"),
                TRANSLATE(
                    "Interface {name} deleted.\nUse [a] from the list to apply changes."
                ).format(name=iface_name),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _edit_interface(self, stdscr, session, iface: dict) -> None:
        iface_id = iface.get("id") or iface.get("name")
        iface_name = iface.get("name", iface_id)

        try:
            failover_licensed = session.call(Method.FAILOVER_LICENSED)
        except Exception:
            failover_licensed = False

        fields = _build_edit_fields(stdscr, session, iface, failover_licensed)
        if fields is None:
            # Error already shown inside _build_edit_fields
            return

        form = Form(stdscr, f"{TRANSLATE('Interface')}: {iface_name}", fields)
        result = form.run()
        if result is None:
            return

        payload = _collect_payload(result, iface, failover_licensed, is_create=False)
        if isinstance(payload, str):
            message_dialog(stdscr, TRANSLATE("Error"), payload)
            return

        try:
            session.call(Method.INTERFACE_UPDATE, iface_id, payload)
            message_dialog(
                stdscr,
                TRANSLATE("Saved"),
                TRANSLATE(
                    "Interface {name} updated.\nUse [a] from the list to apply changes."
                ).format(name=iface_name),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))

    def _create_interface(self, stdscr, session) -> None:
        # Step 1 – pick type, name, description
        step1_fields = [
            ChoiceField(
                key="type",
                label=TRANSLATE("Interface Type"),
                choices=_IFACE_TYPES,
                value=0,
            ),
            FormField(key="name", label=TRANSLATE("Name"), value=""),
            FormField(key="description", label=TRANSLATE("Description"), value=""),
        ]
        form1 = Form(stdscr, TRANSLATE("New Interface – Step 1"), step1_fields)
        r1 = form1.run()
        if r1 is None:
            return

        iface_type = r1["type"]
        iface_name = r1["name"].strip()
        description = r1["description"].strip()

        if not iface_name:
            message_dialog(
                stdscr, TRANSLATE("Error"), TRANSLATE("Interface name is required.")
            )
            return

        # Build a stub iface dict so _build_edit_fields can re-use the same logic
        stub_iface = {
            "name": iface_name,
            "type": iface_type,
            "description": description,
            "ipv4_dhcp": False,
            "ipv6_auto": False,
            "aliases": [],
            "failover_critical": False,
            "failover_group": 1,
            "failover_aliases": [],
            "failover_virtual_aliases": [],
            "bridge_members": [],
            "lag_protocol": "LACP",
            "lag_ports": [],
            "xmit_hash_policy": "LAYER2+3",
            "lacpdu_rate": "SLOW",
            "vlan_parent_interface": "",
            "vlan_tag": 1,
            "vlan_pcp": 0,
            "mtu": 0,
        }

        try:
            failover_licensed = session.call(Method.FAILOVER_LICENSED)
        except Exception:
            failover_licensed = False

        fields = _build_edit_fields(
            stdscr, session, stub_iface, failover_licensed, name_readonly=False
        )
        if fields is None:
            return

        form2 = Form(stdscr, TRANSLATE("New Interface – Step 2"), fields)
        result = form2.run()
        if result is None:
            return

        payload = _collect_payload(
            result, stub_iface, failover_licensed, is_create=True
        )
        if isinstance(payload, str):
            message_dialog(stdscr, TRANSLATE("Error"), payload)
            return

        # Add top-level create-only fields
        payload["type"] = iface_type
        payload["name"] = iface_name
        payload["description"] = description

        try:
            session.call(Method.INTERFACE_CREATE, payload)
            message_dialog(
                stdscr,
                TRANSLATE("Created"),
                TRANSLATE(
                    "Interface {name} created.\nUse [a] from the list to apply changes."
                ).format(name=iface_name),
            )
        except Exception as e:
            message_dialog(stdscr, TRANSLATE("Error"), format_error(e))


def _build_edit_fields(
    stdscr, session, iface: dict, failover_licensed: bool, name_readonly: bool = True
) -> list | None:
    """
    Build the list of FormField instances for the interface edit/create form.
    Returns the field list or None if a prerequisite API call failed.
    """
    iface_type = iface.get("type", "PHYSICAL")
    fields: list = []

    fields.append(SectionField(key="", label=TRANSLATE("Interface Settings")))
    fields.append(
        FormField(
            key="name",
            label=TRANSLATE("Name"),
            value=iface.get("name", ""),
            readonly=name_readonly,
        )
    )
    fields.append(
        FormField(
            key="description",
            label=TRANSLATE("Description"),
            value=iface.get("description", ""),
        )
    )

    # DHCP / IPv6 auto: only when NOT HA-licensed (mirrors midcli)
    if not failover_licensed:
        fields.append(
            BoolField(
                key="ipv4_dhcp",
                label=TRANSLATE("IPv4 DHCP"),
                value=iface.get("ipv4_dhcp", False),
            )
        )
        fields.append(
            BoolField(
                key="ipv6_auto",
                label=TRANSLATE("IPv6 Auto"),
                value=iface.get("ipv6_auto", False),
            )
        )

    fields.append(
        ListField(
            key="_aliases",
            label=TRANSLATE("Aliases (CIDR)"),
            value=[
                _alias_str(a)
                for a in iface.get("aliases", [])
                if a.get("type") in ("INET", "INET6")
            ],
            item_label=TRANSLATE("Address"),
            item_validator=_validate_alias_str,
        )
    )

    if failover_licensed:
        fields.append(SectionField(key="", label=TRANSLATE("Failover Settings")))
        fields.append(
            BoolField(
                key="failover_critical",
                label=TRANSLATE("Failover Critical"),
                value=iface.get("failover_critical", False),
            )
        )
        fields.append(
            IntField(
                key="failover_group",
                label=TRANSLATE("Failover Group"),
                value=iface.get("failover_group") or 1,
                min_val=1,
            )
        )
        fields.append(
            ListField(
                key="_failover_aliases",
                label=TRANSLATE("This Node IPs"),
                value=[a.get("address", "") for a in iface.get("failover_aliases", [])],
                item_label=TRANSLATE("IP Address"),
                item_validator=_validate_ip_only,
            )
        )
        fields.append(
            ListField(
                key="_failover_virtual_aliases",
                label=TRANSLATE("Virtual IPs"),
                value=[
                    a.get("address", "")
                    for a in iface.get("failover_virtual_aliases", [])
                ],
                item_label=TRANSLATE("IP Address"),
                item_validator=_validate_ip_only,
            )
        )

    if iface_type == "VLAN":
        try:
            choices_dict = session.call(Method.INTERFACE_VLAN_PARENT_INTERFACE_CHOICES)
            choices = (
                sorted(choices_dict.keys())
                if isinstance(choices_dict, dict)
                else sorted(choices_dict)
            )
        except Exception as e:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("Could not load VLAN parent choices:\n") + format_error(e),
            )
            return None
        fields.append(SectionField(key="", label=TRANSLATE("VLAN Settings")))
        fields.append(
            ChoiceField(
                key="vlan_parent_interface",
                label=TRANSLATE("Parent Interface"),
                choices=choices,
                value=_choice_idx(choices, iface.get("vlan_parent_interface", "")),
            )
        )
        fields.append(
            IntField(
                key="vlan_tag",
                label=TRANSLATE("VLAN Tag"),
                value=iface.get("vlan_tag") or 1,
                min_val=1,
                max_val=4094,
            )
        )
        fields.append(
            IntField(
                key="vlan_pcp",
                label=TRANSLATE("Priority (PCP)"),
                value=iface.get("vlan_pcp") or 0,
                min_val=0,
                max_val=7,
            )
        )

    elif iface_type == "BRIDGE":
        try:
            choices_dict = session.call(
                Method.INTERFACE_BRIDGE_MEMBERS_CHOICES, iface.get("name", "")
            )
            choices = (
                sorted(choices_dict.keys())
                if isinstance(choices_dict, dict)
                else sorted(choices_dict)
            )
        except Exception as e:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("Could not load bridge member choices:\n") + format_error(e),
            )
            return None
        fields.append(SectionField(key="", label=TRANSLATE("Bridge Settings")))
        fields.append(
            ListField(
                key="bridge_members",
                label=TRANSLATE("Members"),
                value=list(iface.get("bridge_members", [])),
                item_label=TRANSLATE("Interface"),
                item_validator=lambda v, c=choices: (
                    None if v in c else TRANSLATE("Not a valid member: {v}").format(v=v)
                ),
            )
        )

    elif iface_type == "LINK_AGGREGATION":
        try:
            port_dict = session.call(
                Method.INTERFACE_LAG_PORTS_CHOICES, iface.get("name", "")
            )
            port_choices = (
                sorted(port_dict.keys())
                if isinstance(port_dict, dict)
                else sorted(port_dict)
            )
        except Exception as e:
            message_dialog(
                stdscr,
                TRANSLATE("Error"),
                TRANSLATE("Could not load LAG port choices:\n") + format_error(e),
            )
            return None
        fields.append(
            SectionField(key="", label=TRANSLATE("Link Aggregation Settings"))
        )
        fields.append(
            ChoiceField(
                key="lag_protocol",
                label=TRANSLATE("Protocol"),
                choices=_LAG_PROTOCOLS,
                value=_choice_idx(_LAG_PROTOCOLS, iface.get("lag_protocol", "LACP")),
            )
        )
        fields.append(
            ListField(
                key="lag_ports",
                label=TRANSLATE("Ports"),
                value=list(iface.get("lag_ports", [])),
                item_label=TRANSLATE("Port"),
                item_validator=lambda v, c=port_choices: (
                    None if v in c else TRANSLATE("Not a valid port: {v}").format(v=v)
                ),
            )
        )
        fields.append(
            ChoiceField(
                key="xmit_hash_policy",
                label=TRANSLATE("Xmit Hash Policy"),
                choices=_XMIT_POLICIES,
                value=_choice_idx(
                    _XMIT_POLICIES, iface.get("xmit_hash_policy", "LAYER2+3")
                ),
            )
        )
        fields.append(
            ChoiceField(
                key="lacpdu_rate",
                label=TRANSLATE("LACPDU Rate"),
                choices=_LACPDU_RATES,
                value=_choice_idx(_LACPDU_RATES, iface.get("lacpdu_rate", "SLOW")),
            )
        )

    fields.append(SectionField(key="", label=TRANSLATE("Other Settings")))
    fields.append(
        IntField(
            key="mtu",
            label=TRANSLATE("MTU"),
            value=iface.get("mtu") or 0,
            min_val=0,
            max_val=9000,
            help_text=TRANSLATE("Set to 0 to use the system default MTU"),
        )
    )

    return fields


def _collect_payload(
    result: dict, iface: dict, failover_licensed: bool, is_create: bool
) -> dict | str:
    """
    Convert form result into an API payload dict.
    Returns the dict on success or an error string on failure.
    """
    iface_type = iface.get("type", "PHYSICAL")
    payload: dict = {}

    # description (may be in result if name_readonly=False in create step-2,
    # or always in the edit form)
    if "description" in result:
        payload["description"] = result["description"]

    # DHCP / IPv6 auto
    if failover_licensed:
        payload["ipv4_dhcp"] = False
        payload["ipv6_auto"] = False
    else:
        if "ipv4_dhcp" in result:
            payload["ipv4_dhcp"] = bool(result["ipv4_dhcp"])
        if "ipv6_auto" in result:
            payload["ipv6_auto"] = bool(result["ipv6_auto"])

    # Aliases
    alias_result = _aliases_to_payload(result.get("_aliases", []))
    if isinstance(alias_result, str):
        return alias_result
    payload["aliases"] = alias_result

    # Failover fields (HA only)
    if failover_licensed:
        if "failover_critical" in result:
            payload["failover_critical"] = bool(result["failover_critical"])
        if "failover_group" in result:
            payload["failover_group"] = int(result["failover_group"])
        # failover_aliases
        fa_list = result.get("_failover_aliases", [])
        fa_payload = []
        for s in fa_list:
            err = _validate_ip_only(s)
            if err:
                return err
            fa_payload.append(_parse_ip_only(s))
        payload["failover_aliases"] = fa_payload
        # failover_virtual_aliases
        fva_list = result.get("_failover_virtual_aliases", [])
        fva_payload = []
        for s in fva_list:
            err = _validate_ip_only(s)
            if err:
                return err
            fva_payload.append(_parse_ip_only(s))
        payload["failover_virtual_aliases"] = fva_payload

    # Type-specific
    if iface_type == "VLAN":
        if "vlan_parent_interface" in result:
            payload["vlan_parent_interface"] = result["vlan_parent_interface"]
        if "vlan_tag" in result:
            payload["vlan_tag"] = int(result["vlan_tag"])
        if "vlan_pcp" in result:
            payload["vlan_pcp"] = int(result["vlan_pcp"])
    elif iface_type == "BRIDGE":
        if "bridge_members" in result:
            payload["bridge_members"] = list(result["bridge_members"])
    elif iface_type == "LINK_AGGREGATION":
        if "lag_protocol" in result:
            payload["lag_protocol"] = result["lag_protocol"]
        if "lag_ports" in result:
            payload["lag_ports"] = list(result["lag_ports"])
        if "xmit_hash_policy" in result:
            payload["xmit_hash_policy"] = result["xmit_hash_policy"]
        if "lacpdu_rate" in result:
            payload["lacpdu_rate"] = result["lacpdu_rate"]

    # MTU — send None if 0 (API treats 0/None as "use default")
    mtu_val = result.get("mtu", 0)
    payload["mtu"] = None if (isinstance(mtu_val, int) and mtu_val == 0) else mtu_val

    return payload
