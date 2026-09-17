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
"""

import curses
import ipaddress

from truenas_tui.localization import TRANSLATE
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

_LAG_PROTOCOLS = ["LACP", "FAILOVER", "LOADBALANCE", "ROUNDROBIN", "NONE"]
_XMIT_POLICIES = ["LAYER2", "LAYER2+3", "LAYER3+4"]
_LACPDU_RATES = ["SLOW", "FAST"]
_IFACE_TYPES = ["BRIDGE", "LINK_AGGREGATION", "VLAN"]

# Form result keys copied straight into the API payload, per interface type.
_TYPE_KEYS = {
    "VLAN": ("vlan_parent_interface", "vlan_tag", "vlan_pcp"),
    "BRIDGE": ("bridge_members",),
    "LINK_AGGREGATION": (
        "lag_protocol",
        "lag_ports",
        "xmit_hash_policy",
        "lacpdu_rate",
    ),
}


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

    configured = []
    for a in aliases:
        if a.get("type") in ("INET", "INET6"):
            configured.append(_alias_str(a))
    active = []
    for a in state_aliases:
        if a.get("type") in ("INET", "INET6"):
            active.append(_alias_str(a))

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


def _load_choices(stdscr, session, error_prefix: str, method: str, *args):
    """Sorted names from an interface.*_choices call, or None after showing the error."""
    try:
        return sorted(session.call(method, *args))
    except Exception as e:
        message_dialog(stdscr, TRANSLATE("Error"), error_prefix + format_error(e))
        return None


class NetworkInterfacePlugin(BasePlugin):
    REQUIRED_WRITE_ROLES = frozenset({"NETWORK_INTERFACE_WRITE"})
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
        selected = 0
        ifaces = None  # None → reload the list and status before drawing
        status = ""
        stdscr.keypad(True)
        curses.curs_set(0)

        while True:
            if ifaces is None:
                try:
                    ifaces = session.call("interface.query")
                except Exception as e:
                    message_dialog(stdscr, TRANSLATE("Error"), format_error(e))
                    return
                status = self._get_status(session)
                selected = min(selected, max(0, len(ifaces) - 1))

            self._draw_list(stdscr, ifaces, selected, status)
            key = stdscr.getch()

            if key == 4:
                raise HardExit()
            elif key in (27, ord("q")):
                return
            elif key == curses.KEY_UP:
                selected = max(0, selected - 1)
            elif key == curses.KEY_DOWN:
                selected = min(max(0, len(ifaces) - 1), selected + 1)
            elif key in (ord("\n"), ord("\r"), curses.KEY_ENTER) and ifaces:
                self._edit_interface(stdscr, session, ifaces[selected])
                ifaces = None
            elif key == ord("n"):
                self._create_interface(stdscr, session)
                ifaces = None
            elif key == ord("d") and ifaces:
                self._delete_interface(stdscr, session, ifaces[selected])
                ifaces = None
            elif key == ord("a"):
                self._apply_changes(stdscr, session)
                ifaces = None
            elif key == ord("p"):
                self._persist_changes(stdscr, session)
                ifaces = None

    def _get_status(self, session) -> str:
        try:
            waiting = session.call("interface.checkin_waiting")
            if waiting is not None:
                return TRANSLATE(
                    "Changes applied. Press [p] to persist or they roll back in {n}s."
                ).format(n=int(waiting))
            if session.call("interface.has_pending_changes"):
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
            session.call("interface.commit")
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
            session.call("interface.checkin")
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
            session.call("interface.delete", iface_id)
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
            failover_licensed = session.call("failover.licensed")
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

        payload = _collect_payload(result, iface, failover_licensed)
        if isinstance(payload, str):
            message_dialog(stdscr, TRANSLATE("Error"), payload)
            return

        try:
            session.call("interface.update", iface_id, payload)
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
            failover_licensed = session.call("failover.licensed")
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

        payload = _collect_payload(result, stub_iface, failover_licensed)
        if isinstance(payload, str):
            message_dialog(stdscr, TRANSLATE("Error"), payload)
            return

        # Add top-level create-only fields
        payload["type"] = iface_type
        payload["name"] = iface_name
        payload["description"] = description

        try:
            session.call("interface.create", payload)
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
    fields: list = [
        SectionField(key="", label=TRANSLATE("Interface Settings")),
        FormField(
            key="name",
            label=TRANSLATE("Name"),
            value=iface.get("name", ""),
            readonly=name_readonly,
        ),
        FormField(
            key="description",
            label=TRANSLATE("Description"),
            value=iface.get("description", ""),
        ),
    ]

    # DHCP / IPv6 auto: only when NOT HA-licensed (mirrors midcli)
    if not failover_licensed:
        fields += [
            BoolField(
                key="ipv4_dhcp",
                label=TRANSLATE("IPv4 DHCP"),
                value=iface.get("ipv4_dhcp", False),
            ),
            BoolField(
                key="ipv6_auto",
                label=TRANSLATE("IPv6 Auto"),
                value=iface.get("ipv6_auto", False),
            ),
        ]

    alias_strs = []
    for a in iface.get("aliases", []):
        if a.get("type") in ("INET", "INET6"):
            alias_strs.append(_alias_str(a))
    fields.append(
        ListField(
            key="_aliases",
            label=TRANSLATE("Aliases (CIDR)"),
            value=alias_strs,
            item_label=TRANSLATE("Address"),
            item_validator=_validate_alias_str,
        )
    )

    if failover_licensed:
        node_ips = []
        for a in iface.get("failover_aliases", []):
            node_ips.append(a.get("address", ""))
        virtual_ips = []
        for a in iface.get("failover_virtual_aliases", []):
            virtual_ips.append(a.get("address", ""))
        fields += [
            SectionField(key="", label=TRANSLATE("Failover Settings")),
            BoolField(
                key="failover_critical",
                label=TRANSLATE("Failover Critical"),
                value=iface.get("failover_critical", False),
            ),
            IntField(
                key="failover_group",
                label=TRANSLATE("Failover Group"),
                value=iface.get("failover_group") or 1,
                min_val=1,
            ),
            ListField(
                key="_failover_aliases",
                label=TRANSLATE("This Node IPs"),
                value=node_ips,
                item_label=TRANSLATE("IP Address"),
                item_validator=_validate_ip_only,
            ),
            ListField(
                key="_failover_virtual_aliases",
                label=TRANSLATE("Virtual IPs"),
                value=virtual_ips,
                item_label=TRANSLATE("IP Address"),
                item_validator=_validate_ip_only,
            ),
        ]

    if iface_type == "VLAN":
        choices = _load_choices(
            stdscr,
            session,
            TRANSLATE("Could not load VLAN parent choices:\n"),
            "interface.vlan_parent_interface_choices",
        )
        if choices is None:
            return None
        fields += [
            SectionField(key="", label=TRANSLATE("VLAN Settings")),
            ChoiceField(
                key="vlan_parent_interface",
                label=TRANSLATE("Parent Interface"),
                choices=choices,
                value=_choice_idx(choices, iface.get("vlan_parent_interface", "")),
            ),
            IntField(
                key="vlan_tag",
                label=TRANSLATE("VLAN Tag"),
                value=iface.get("vlan_tag") or 1,
                min_val=1,
                max_val=4094,
            ),
            IntField(
                key="vlan_pcp",
                label=TRANSLATE("Priority (PCP)"),
                value=iface.get("vlan_pcp") or 0,
                min_val=0,
                max_val=7,
            ),
        ]

    elif iface_type == "BRIDGE":
        choices = _load_choices(
            stdscr,
            session,
            TRANSLATE("Could not load bridge member choices:\n"),
            "interface.bridge_members_choices",
            iface.get("name", ""),
        )
        if choices is None:
            return None
        fields += [
            SectionField(key="", label=TRANSLATE("Bridge Settings")),
            ListField(
                key="bridge_members",
                label=TRANSLATE("Members"),
                value=list(iface.get("bridge_members", [])),
                item_label=TRANSLATE("Interface"),
                item_validator=lambda v, c=choices: (
                    None if v in c else TRANSLATE("Not a valid member: {v}").format(v=v)
                ),
            ),
        ]

    elif iface_type == "LINK_AGGREGATION":
        port_choices = _load_choices(
            stdscr,
            session,
            TRANSLATE("Could not load LAG port choices:\n"),
            "interface.lag_ports_choices",
            iface.get("name", ""),
        )
        if port_choices is None:
            return None
        fields += [
            SectionField(key="", label=TRANSLATE("Link Aggregation Settings")),
            ChoiceField(
                key="lag_protocol",
                label=TRANSLATE("Protocol"),
                choices=_LAG_PROTOCOLS,
                value=_choice_idx(_LAG_PROTOCOLS, iface.get("lag_protocol", "LACP")),
            ),
            ListField(
                key="lag_ports",
                label=TRANSLATE("Ports"),
                value=list(iface.get("lag_ports", [])),
                item_label=TRANSLATE("Port"),
                item_validator=lambda v, c=port_choices: (
                    None if v in c else TRANSLATE("Not a valid port: {v}").format(v=v)
                ),
            ),
            ChoiceField(
                key="xmit_hash_policy",
                label=TRANSLATE("Xmit Hash Policy"),
                choices=_XMIT_POLICIES,
                value=_choice_idx(
                    _XMIT_POLICIES, iface.get("xmit_hash_policy", "LAYER2+3")
                ),
            ),
            ChoiceField(
                key="lacpdu_rate",
                label=TRANSLATE("LACPDU Rate"),
                choices=_LACPDU_RATES,
                value=_choice_idx(_LACPDU_RATES, iface.get("lacpdu_rate", "SLOW")),
            ),
        ]

    fields += [
        SectionField(key="", label=TRANSLATE("Other Settings")),
        IntField(
            key="mtu",
            label=TRANSLATE("MTU"),
            value=iface.get("mtu") or 0,
            min_val=0,
            max_val=9000,
            help_text=TRANSLATE("Set to 0 to use the system default MTU"),
        ),
    ]

    return fields


def _collect_payload(result: dict, iface: dict, failover_licensed: bool) -> dict | str:
    """
    Convert form result into an API payload dict.
    Returns the dict on success or an error string on failure.
    """
    payload: dict = {}
    if "description" in result:
        payload["description"] = result["description"]

    # DHCP / IPv6 auto are forced off on HA systems
    if failover_licensed:
        payload["ipv4_dhcp"] = payload["ipv6_auto"] = False
    else:
        for k in ("ipv4_dhcp", "ipv6_auto"):
            if k in result:
                payload[k] = result[k]

    aliases = _aliases_to_payload(result.get("_aliases", []))
    if isinstance(aliases, str):
        return aliases
    payload["aliases"] = aliases

    if failover_licensed:
        for k in ("failover_critical", "failover_group"):
            if k in result:
                payload[k] = result[k]
        for key in ("failover_aliases", "failover_virtual_aliases"):
            ips = result.get("_" + key, [])
            parsed = []
            for s in ips:
                err = _validate_ip_only(s)
                if err:
                    return err
                parsed.append(_parse_ip_only(s))
            payload[key] = parsed

    type_keys = _TYPE_KEYS.get(iface.get("type", "PHYSICAL"), ())
    for k in type_keys:
        if k in result:
            payload[k] = result[k]

    # MTU — send None if 0 (API treats 0/None as "use default")
    mtu = result.get("mtu", 0)
    payload["mtu"] = None if mtu == 0 else mtu

    return payload
