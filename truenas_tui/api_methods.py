"""
Central registry of all TrueNAS middleware API method strings.

All session.call(...) sites should reference Method.<CONSTANT> rather than
bare string literals so that typos are caught at import time and method
names are easy to locate/update.
"""
from enum import StrEnum


class Method(StrEnum):
    AUTH_ME                         = 'auth.me'
    CORE_PING                       = 'core.ping'
    AUTH_SET_ATTRIBUTE              = 'auth.set_attribute'
    AUTH_GENERATE_ONETIME_PASSWORD  = 'auth.generate_onetime_password'
    AUTH_TWOFACTOR_UPDATE           = 'auth.twofactor.update'
    FAILOVER_LICENSED                       = 'failover.licensed'
    INTERFACE_BRIDGE_MEMBERS_CHOICES        = 'interface.bridge_members_choices'
    INTERFACE_CHECKIN               = 'interface.checkin'
    INTERFACE_CREATE                        = 'interface.create'
    INTERFACE_DELETE                        = 'interface.delete'
    INTERFACE_LAG_PORTS_CHOICES             = 'interface.lag_ports_choices'
    INTERFACE_VLAN_PARENT_INTERFACE_CHOICES = 'interface.vlan_parent_interface_choices'
    INTERFACE_CHECKIN_WAITING       = 'interface.checkin_waiting'
    INTERFACE_COMMIT                = 'interface.commit'
    INTERFACE_HAS_PENDING_CHANGES   = 'interface.has_pending_changes'
    INTERFACE_QUERY                 = 'interface.query'
    INTERFACE_UPDATE                = 'interface.update'
    NETWORK_CONFIGURATION_CONFIG    = 'network.configuration.config'
    NETWORK_CONFIGURATION_UPDATE    = 'network.configuration.update'
    PRIVILEGE_LOCAL_ADMINISTRATORS  = 'privilege.local_administrators'
    STATICROUTE_CREATE              = 'staticroute.create'
    STATICROUTE_DELETE              = 'staticroute.delete'
    STATICROUTE_QUERY               = 'staticroute.query'
    STATICROUTE_UPDATE              = 'staticroute.update'
    SYSTEM_CONFIG_RESET             = 'system.config.reset'
    SYSTEM_GENERAL_GET_UI_URLS      = 'system.general.get_ui_urls'
    SYSTEM_INFO                     = 'system.info'
    SYSTEM_REBOOT                   = 'system.reboot'
    SYSTEM_SHUTDOWN                 = 'system.shutdown'
    USER_HAS_LOCAL_ADMINISTRATOR_SET_UP = 'user.has_local_administrator_set_up'
    USER_RENEW_2FA_SECRET           = 'user.renew_2fa_secret'
    USER_SET_PASSWORD               = 'user.set_password'
    USER_SETUP_LOCAL_ADMINISTRATOR  = 'user.setup_local_administrator'
    USER_UNSET_2FA_SECRET           = 'user.unset_2fa_secret'
    USER_UPDATE                     = 'user.update'
