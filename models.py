"""
ADVA Ensemble Connector — data models.

Provides configuration model classes for interfaces, services, VNFs,
firewall profiles, and TACACS with unified JSON serialisation.
"""

import json
import ipaddress
from dataclasses import dataclass, field, asdict, InitVar
from typing import Any, ClassVar


# ---------------------------------------------------------------------------
#  Utilities
# ---------------------------------------------------------------------------

def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def response_format(response, jso=False):
    if jso:
        return json.loads(response)
    return json.dumps(response, indent=3)


def get_short_list(response, field_name):
    return [item[field_name] for item in response]



# ===========================================================================
#  Serialisation helpers
# ===========================================================================

def _to_api_dict(obj, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """
    Convert an object's ``__dict__`` to an API-ready dict:
      - underscores in keys → hyphens
      - keys listed in *exclude* are dropped
    """
    exclude = exclude or set()
    return {
        k.replace('_', '-'): v
        for k, v in vars(obj).items()
        if k not in exclude
    }


def _dc_get_config(self, jsn: bool = True) -> str | dict:
    """Shared ``get_config()`` for dataclass-based models."""
    config = {
        k.replace('_', '-'): v
        for k, v in asdict(self).items()
    }
    return json.dumps(config) if jsn else config


class _Serialisable:
    """
    Mixin providing unified ``get_config()`` for regular (non-dataclass) models.

    Subclasses can set ``_config_exclude`` to drop internal fields.
    """
    _config_exclude: set[str] = set()

    def get_config(self, jsn: bool = True) -> str | dict:
        config = _to_api_dict(self, exclude=self._config_exclude)
        return json.dumps(config) if jsn else config


# Backward-compatible alias
Config = _Serialisable


# ===========================================================================
#  Interface hierarchy
# ===========================================================================

class Interface(_Serialisable):
    _config_exclude = {'type'}

    def __init__(self, name='', alias='', ip_addr='', owner_tag='',
                 firewall_profile='', admin='', type=''):
        self.name = name
        self.alias = alias
        self.ip_addr = ip_addr
        self.owner_tag = owner_tag
        self.firewall_profile = firewall_profile
        self.admin = admin
        self.type = type

    def get_config(self, jsn: bool = True) -> str | dict:
        exclude = set(self._config_exclude)
        if self.type == 'aggregation':
            exclude.add('admin')
        config = _to_api_dict(self, exclude=exclude)
        return json.dumps(config) if jsn else config


class IpInterface(Interface):

    def __init__(self, name='', alias='', ip_addr='', owner_tag='',
                 firewall_profile='', admin='up', l3shunt='disable'):
        super().__init__(name=name, alias=alias, ip_addr=ip_addr,
                         owner_tag=owner_tag, firewall_profile=firewall_profile,
                         admin=admin, type='ip')
        self.l3shunt = l3shunt


class VPort(Interface):

    def __init__(self, name='', alias='', ip_addr='', owner_tag='',
                 firewall_profile='', vlan_id=0, port_type='vhost',
                 admin='up', dev_name='', domain='default',
                 dequeue_shaper_rate=0, uplink_status_propagation='enable'):
        super().__init__(name=name, alias=alias, ip_addr=ip_addr,
                         owner_tag=owner_tag, firewall_profile=firewall_profile,
                         admin=admin, type='vport')
        self.alias = alias
        self.dev_name = dev_name if dev_name else self.name
        self.domain = domain
        self.dequeue_shaper_rate = dequeue_shaper_rate
        self.vlan_id = vlan_id
        self.uplink_status_propagation = uplink_status_propagation
        self.port_type = port_type


class GigabitEthernet(Interface):
    """
    Unified gigabit ethernet interface.

    Accepts LLDP / tunnel settings in two forms (backward-compatible):
      - As pre-built dicts: ``lldp={...}, tunnel={...}``
      - As individual keyword arguments: ``lldp_da=..., tun_cdp_vtp_udld=...``

    When both a dict and individual args are supplied, the dict takes priority.
    """

    _LLDP_DEFAULTS = {'da': 'nearest-bridge', 'mode': 'tx-and-rx'}
    _TUNNEL_DEFAULTS = {
        'cdp-vtp-udld': 'disable', 'elmi': 'disable', 'esmc': 'disable',
        'garp-mrp': 'disable', 'lacp': 'disable', 'lamp': 'disable',
        'lldp': 'disable', 'loam': 'disable', 'port-auth': 'disable',
        'ptp-pdelay': 'disable', 'stp': 'disable', 'vstp': 'disable',
    }

    def __init__(self, name='', alias='', ip_addr='', owner_tag='',
                 firewall_profile='', admin='up', duplex='full',
                 auto_negotiation='enable', crossover='automatic',
                 speed=1000, sr_iov='disable', mtu=9600,
                 master_slave='auto-prefer-slave', output_rate='1000000000',
                 attach='true', reserved_mac='disable',
                 oam='disable', oam_activity='active', oam_loopback='enable',
                 lldp=None, tunnel=None,
                 lldp_da=None, lldp_mode=None,
                 tun_cdp_vtp_udld=None, tun_elmi=None, tun_esmc=None,
                 tun_garp_mrp=None, tun_lacp=None, tun_lamp=None,
                 tun_lldp=None, tun_loam=None, tun_port_auth=None,
                 tun_ptp_pdelay=None, tun_stp=None, tun_vstp=None,
                 link_loss_forward=None):
        super().__init__(name=name, alias=alias, ip_addr=ip_addr,
                         owner_tag=owner_tag, firewall_profile=firewall_profile,
                         admin=admin, type='gigabit')

        self.duplex = duplex
        self.auto_negotiation = auto_negotiation
        self.crossover = crossover
        self.speed = speed
        self.sr_iov = sr_iov
        self.mtu = mtu
        self.master_slave = master_slave
        self.output_rate = output_rate
        self.reserved_mac = reserved_mac
        self.oam = oam
        self.oam_activity = oam_activity
        self.oam_loopback = oam_loopback
        self.attach = attach
        self.link_loss_forward = link_loss_forward or []

        if lldp is not None:
            self.lldp = lldp
        else:
            self.lldp = {
                'da': lldp_da or self._LLDP_DEFAULTS['da'],
                'mode': lldp_mode or self._LLDP_DEFAULTS['mode'],
            }

        if tunnel is not None:
            self.tunnel = tunnel
        else:
            tun_args = {
                'cdp-vtp-udld': tun_cdp_vtp_udld, 'elmi': tun_elmi,
                'esmc': tun_esmc, 'garp-mrp': tun_garp_mrp,
                'lacp': tun_lacp, 'lamp': tun_lamp, 'lldp': tun_lldp,
                'loam': tun_loam, 'port-auth': tun_port_auth,
                'ptp-pdelay': tun_ptp_pdelay, 'stp': tun_stp, 'vstp': tun_vstp,
            }
            self.tunnel = {
                k: (v if v is not None else self._TUNNEL_DEFAULTS[k])
                for k, v in tun_args.items()
            }


# Backward-compatible alias
GigabitEthernet1 = GigabitEthernet


# ===========================================================================
#  Dataclass-based models
# ===========================================================================

@dataclass
class AggregationMember:
    name: str = ''
    activity: str = ''
    actor_timeout: str = 'short'
    actor_port_priority: int = 0
    group_name: str = 'ag-1'

    get_config = _dc_get_config


class Aggregation(Interface):

    def __init__(self, name='', alias='', ip_addr='', owner_tag='',
                 firewall_profile='', lacp='enable', load_balance='srcdstmac',
                 max_active_members=2, actor_system_priority=65535,
                 members=None):
        super().__init__(name=name, alias=alias, ip_addr=ip_addr,
                         owner_tag=owner_tag,
                         firewall_profile=firewall_profile, type='aggregation')
        self.lacp = lacp
        self.load_balance = load_balance
        self.max_active_members = max_active_members
        self.self_actor_system_priority = actor_system_priority
        self.members = members or []


@dataclass
class Service:
    name: str = ''
    type: str = 'e-lan'
    fib_limit: str = '65000'
    learning: str = 'enable'
    storm_control: str = '1000'
    owner_tag: str = ''
    domain: str = 'default'
    l4_port_range: str = '49152-49183'
    serviceports: list = field(default_factory=list)

    get_config = _dc_get_config


@dataclass
class ServicePort:
    UNTAGGED: ClassVar[str] = 'untagged * * * *'
    TAGGED:   ClassVar[str] = 'tagged * * * *'
    TRUNK:    ClassVar[str] = '* * * * *'

    name: str = ''
    interface: str = ''
    owner_tag: str = ''
    alias: str = ''
    qos: str = 'default'
    rate: str = ''
    priority: str = '0'
    pbit: str = '0'
    dscp: str = '0'
    dei: str = '0'
    layer2: str = '0'
    ingress: str = 'fwd'
    egress: str = 'fwd'
    matchrules: list = field(default_factory=list)
    root: str = '0'
    connector_chain_port: str = '0'
    vnf_chain_port: str = '0'
    mode: InitVar[str] = 'access'
    vlan: InitVar[int] = 0
    allowed_vlans: InitVar[str] = ''

    get_config = _dc_get_config

    def __post_init__(self, mode: str, vlan: int, allowed_vlans: str):
        if mode in ('access', 'native_vlan') and vlan:
            if not self.matchrules:
                self.matchrules = [{'name': '10', 'rule': self.UNTAGGED}]
            if self.ingress == 'fwd':
                self.ingress = f"push {vlan} p-bit c-vlan-tpid passdei"
            if self.egress == 'fwd':
                self.egress = 'pop'
        elif mode == 'tagged':
            if not self.matchrules:
                self.matchrules = (self._parse_allowed_vlans(allowed_vlans)
                                   if allowed_vlans
                                   else [{'name': '10', 'rule': self.TAGGED}])
        elif mode == 'trunk':
            if not self.matchrules:
                self.matchrules = (self._parse_allowed_vlans(allowed_vlans)
                                   if allowed_vlans
                                   else [{'name': '10', 'rule': self.TRUNK}])

    @staticmethod
    def _parse_allowed_vlans(allowed_vlans: str) -> list:
        rules = []
        for i, entry in enumerate(allowed_vlans.split(','), start=1):
            rules.append({'name': str(i * 10), 'rule': f"{entry.strip()} * * *"})
        return rules



@dataclass
class VnfProfile:
    name: str = ''
    vcpus: int = 1
    maxMem: int = 512
    cpuExcl: int = 1

    get_config = _dc_get_config


# ---------------------------------------------------------------------------
#  Firewall
# ---------------------------------------------------------------------------

class InvalidPortNumber(Exception):
    pass


class InvalidState(Exception):
    pass


class InvalidDirection(Exception):
    pass


class InvalidProtocol(Exception):
    pass


@dataclass
class FirewallPort:
    VALID_STATES: set = field(default=frozenset({"enable", "disable"}), init=False, repr=False)
    VALID_DIRECTIONS: set = field(default=frozenset({"incoming"}), init=False, repr=False)
    VALID_PROTOCOLS: set = field(default=frozenset({"tcp", "udp", "all"}), init=False, repr=False)

    port: str = ""
    state: str = "enable"
    protocol: str = "tcp"
    direction: str = "incoming"

    def __post_init__(self):
        if not self._is_valid_port(self.port):
            raise InvalidPortNumber(f"Bad port Number {self.port}")
        if self.state not in self.VALID_STATES:
            raise InvalidState(f"Invalid state {self.state}. Allowed: {self.VALID_STATES}")
        if self.protocol not in self.VALID_PROTOCOLS:
            raise InvalidProtocol(f"Invalid protocol {self.protocol}. Allowed: {self.VALID_PROTOCOLS}")
        if self.direction not in self.VALID_DIRECTIONS:
            raise InvalidDirection(f"Invalid direction {self.direction}. Allowed: {self.VALID_DIRECTIONS}")

    @staticmethod
    def _is_valid_port(port):
        try:
            num = int(port)
            return 1 <= num <= 65535
        except (ValueError, TypeError):
            return False

    def get_config(self, jsn: bool = True) -> str | dict:
        config = {
            k.replace('_', '-'): v
            for k, v in asdict(self).items()
            if not k.startswith('VALID_')
        }
        return json.dumps(config) if jsn else config


@dataclass
class FirewallProfile:
    name: str = ""
    firewallports: list = field(default_factory=list)

    get_config = _dc_get_config


# ---------------------------------------------------------------------------
#  VNF  (conditional attributes — regular classes with _Serialisable)
# ---------------------------------------------------------------------------

class Vnf(_Serialisable):
    """VNF definition."""

    def __init__(self, name: str = '', image: str = '', profile: str = "",
                 admin: str = "down", secondary_disk: str = None,
                 vnfdef: str = None, ethports=None,
                 cloudinit_meta_data: str = None, cloudinit_user_data: str = None,
                 cloudinit_config_drive: str = None, cloudinit_enable: str = 'disable'):
        self.name = name
        self.image = image
        self.profile = profile
        self.admin = admin
        self.ethports = ethports or []
        if vnfdef:
            self.vnfdef = vnfdef
        if secondary_disk:
            self.secondary_disk = secondary_disk
        if cloudinit_meta_data:
            self.cloud_init_meta_data = cloudinit_meta_data
        if cloudinit_user_data:
            self.cloud_init_user_data = cloudinit_user_data
        if cloudinit_config_drive:
            self.cloudinit_config_drive = cloudinit_config_drive
        self.cloudinit_enable = cloudinit_enable


class VnfPort(_Serialisable):
    """VNF port."""

    def __init__(self, name: str = '', admin: str = 'down', mac: str = None,
                 connection: str = '', queues: int = 1):
        self.name = name
        self.admin = admin
        if mac:
            self.mac = mac
        self.connection = connection
        if queues > 1:
            self.queues = queues


# ---------------------------------------------------------------------------
#  TACACS
# ---------------------------------------------------------------------------

class TacacsServer(_Serialisable):

    def __init__(self, ip_server='', ip_client='', key='', timeout='5'):
        if not is_valid_ip(ip_server.strip()):
            raise ValueError(f"Invalid server IP: '{ip_server}'")
        if not is_valid_ip(ip_client.strip()):
            raise ValueError(f"Invalid client IP: '{ip_client}'")
        self.ip_server = ip_server
        self.ip_client = ip_client
        self.key = key
        try:
            int(timeout.strip())
            self.timeout = timeout
        except ValueError:
            self.timeout = '5'


class TacacsConfig(_Serialisable):

    _VALID_AUTH_METHODS = {"local", "local,tacacs", "tacacs,local", "tacacs"}
    _VALID_ACCOUNTING = {"enable", "disable"}

    def __init__(self, authholder='local', accounting_enable='disable',
                 tacacs_1=None, tacacs_2=None):
        if accounting_enable in self._VALID_ACCOUNTING:
            self.accounting_enable = accounting_enable
        if authholder in self._VALID_AUTH_METHODS:
            self.authholder = authholder
        self.tacacs_1 = tacacs_1 or {}
        self.tacacs_2 = tacacs_2 or {}
