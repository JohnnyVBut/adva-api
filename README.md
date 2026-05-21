# ADVA Ensemble Connector API — Documentation

## Overview

Python library for managing ADVA Ensemble Connector appliances via REST API. Provides data models for configuring network interfaces, services, VNFs, firewall profiles, and TACACS authentication, as well as a session-based HTTP client with automatic retry and built-in configuration transaction management.

### Project Structure

```
├── adva_api.py      API client (HTTP transport, auto-config, business logic)
├── models.py        Data models (interfaces, services, VNFs, firewall, TACACS)
├── urn_data.py      Endpoint registry (command → URL + HTTP method mapping)
```

### Dependencies

- **Python** ≥ 3.10
- **requests** (includes urllib3)

```bash
pip install requests
```

No other external dependencies required.

---

## Quick Start

```python
import logging
from adva_api import API, VPort, GigabitEthernet, Service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

api = API(url="https://10.0.0.1", username="admin", password="secret")
api.get_token()

# Single call — auto lock → execute → commit
api.configure_interface(VPort(name="vp-1", vlan_id=100))

# Multiple items — one lock → all operations → one commit
api.configure_interface([
    VPort(name="vp-1", vlan_id=100),
    VPort(name="vp-2", vlan_id=200),
    GigabitEthernet(name="ge-1/1", mtu=9000),
])
```

---

## Module Reference

### adva_api.py

Contains the `API` class and re-exports all models from `models.py` for backward compatibility. Any existing code using `from adva_api import VPort, Service` continues to work without changes.

### models.py

Self-contained module with no HTTP dependencies. Can be imported independently for configuration building, testing, or serialisation without pulling in `requests`/`urllib3`.

```python
# Direct import (no HTTP deps)
from models import VPort, Service, GigabitEthernet

# Or through adva_api (includes HTTP)
from adva_api import VPort, Service, GigabitEthernet
```

### urn_data.py

Declarative endpoint registry. Maps command names to API paths and HTTP methods. Created once at module load time (not per call).

```python
from urn_data import get_urn_data

url, method = get_urn_data("config-lock", "https://10.0.0.1", "/")
# → ("https://10.0.0.1/vse/api/v1.0/config/lock/", "POST")
```

---

## Auto-Config Transaction Management

All mutating API methods (`configure_interface`, `delete_interface`, `create_service`, `delete_service`, `create_vnf_profile`) are decorated with `@_auto_config`, which provides automatic transaction management:

- **Standalone call** — if config is not locked, the decorator automatically performs `lock → execute → commit` (or `lock → execute → abandon` on error)
- **Within a transaction** — if config is already locked (by a prior `lock_config()` call), the decorator just executes the method without locking or committing

This means every mutating method works both as a standalone operation and as part of a larger transaction:

```python
# Standalone — each call is its own transaction
api.configure_interface(vport1)
api.create_service(svc1)
api.delete_interface(vport2)

# Manual transaction — multiple operations in one lock/commit
api.lock_config()
api.configure_interface([ge1, ge2])
api.create_service(svc1)
api.delete_interface(old_vport)
api.config_commit()
```

On error, the decorator calls `config_abandon()` and re-raises the exception.

---

## API Class

### Constructor

```python
API(url: str, username: str, password: str, token: str = "")
```

| Parameter  | Description                                      |
|------------|--------------------------------------------------|
| `url`      | Base URL of the appliance (e.g. `https://10.0.0.1`) |
| `username` | API username                                     |
| `password` | API password                                     |
| `token`    | Optional pre-existing auth token                 |

Creates a persistent `requests.Session` with:
- Basic auth (username/password)
- TLS verification disabled (appliances use self-signed certificates)
- Automatic retry (3 attempts, exponential backoff, on 500/502/503/504)
- 10-second timeout per request

---

### Authentication

#### `get_token() → str`

Authenticates against the appliance and stores the session token. Token is also saved to `token.toc` with `0600` permissions for emergency recovery.

```python
token = api.get_token()
```

Raises `EnvironmentError` on authentication failure.

---

### Interface Management

All interface methods accept a single interface or a list. A single item returns a single tuple; a list returns a list of tuples.

#### `configure_interface(config: Interface | list) → tuple | list[tuple]`

Creates or configures one or more interfaces. Decorated with `@_auto_config`.

```python
from adva_api import VPort, GigabitEthernet, IpInterface

# Single
api.configure_interface(VPort(name="vp-1", vlan_id=100))

# Multiple — one transaction
api.configure_interface([
    VPort(name="vp-1", vlan_id=100),
    VPort(name="vp-2", vlan_id=200),
    GigabitEthernet(name="ge-1/1", mtu=9000),
])
```

Raises `TypeError` if any item is not an `Interface` subclass.

#### `delete_interface(config: Interface | list) → tuple | list[tuple]`

Deletes one or more interfaces. Decorated with `@_auto_config`.

```python
api.delete_interface(vport1)
api.delete_interface([vport1, vport2, ge1])
```

---

### Service Management

#### `get_services_list(brief: bool = True)`

Returns list of configured services.

```python
names = api.get_services_list(brief=True)    # → ["svc-1", "svc-2"]
services = api.get_services_list(brief=False) # full details
```

#### `create_service(config: Service | list) → tuple | list[tuple]`

Creates one or more services. Decorated with `@_auto_config`.

```python
svc = Service(name='svc-1', type='e-lan')
api.create_service(svc)

# Multiple
api.create_service([
    Service(name='svc-1', type='e-lan'),
    Service(name='svc-2', type='e-line'),
])
```

#### `delete_service(services: str | Service | list) → tuple | list[tuple]`

Deletes one or more services. Accepts names as strings, `Service` instances, or mixed lists. Decorated with `@_auto_config`.

```python
api.delete_service('svc-1')
api.delete_service(Service(name='svc-1'))
api.delete_service(['svc-1', svc2_instance, 'svc-3'])
```

---

### VNF Management

#### `get_vnf_list(brief: bool = False)`

```python
vnfs = api.get_vnf_list()
names = api.get_vnf_list(brief=True)
```

#### `create_vnf_profile(payload: str) → tuple[int, str]`

Creates a VNF profile from a JSON payload. Decorated with `@_auto_config`.

```python
profile = VnfProfile(name="prof-1", vcpus=4, maxMem=2048)
api.create_vnf_profile(profile.get_config())
```

---

### VNF Image Management

#### `get_image_list(brief: bool = False)`

```python
images = api.get_image_list()
names = api.get_image_list(brief=True)
```

#### `upload_vnf_image(payload) → tuple[int, str]`

Uploads a VNF image.

#### `delete_vnf_image(image_name: str) → str`

Deletes a VNF image by name.

#### `get_image_status(image_name: str) → str | None`

Returns the deployment status of an image, or `None` if not found.

#### `deploy_image(image_config: dict) → str`

Uploads an image and polls until deployment completes. Blocks the calling thread.

```python
result = api.deploy_image({"target-name": "my-vnf-image", ...})
# → "my-vnf-image: complete"
```

---

### Configuration Management

These low-level methods are available for manual transaction control, but most use cases are covered by `@_auto_config` on mutating methods.

#### `lock_config() → tuple[int, str]`

Acquires a configuration lock. Sets `api.config_is_locked = True` on success.

#### `config_locked(force: bool = False) → bool`

Checks if config is locked. If `force=True`, attempts to acquire the lock.

#### `config_commit() → tuple[int, str]`

Commits the working configuration to active.

#### `config_unlock() → int`

Releases the configuration lock. Returns `200` if successful or if config was not locked.

#### `config_abandon(emergency: bool = False)`

Discards uncommitted changes. In emergency mode, reads the token from `token.toc` file (useful for recovery after a crash).

```python
api.config_abandon()                  # normal
api.config_abandon(emergency=True)    # reads token from file
```

---

### Low-level Methods

#### `query(command: str, argument: str = "", payload: str = "") → tuple[int, str]`

Executes any registered command directly. Available commands are defined in `urn_data.py`.

```python
code, result = api.query("get-services")
code, result = api.query("create-service", argument="my-svc", payload=json.dumps({...}))
```

---

## Data Models

All models provide a `get_config()` method that serialises the object to JSON, converting Python attribute names (underscores) to API format (hyphens).

```python
vport = VPort(name="vp-1", vlan_id=100)
print(vport.get_config())
# → {"name": "vp-1", "alias": "", "ip-addr": "", ..., "vlan-id": 100, ...}

# As dict
config_dict = vport.get_config(jsn=False)
```

### Serialisation Architecture

| Base                 | Used by                            | Notes                              |
|----------------------|------------------------------------|------------------------------------|
| `_Serialisable`      | Interface hierarchy, Vnf, VnfPort, TacacsServer/Config | Supports conditional attributes and `_config_exclude` |
| `_dc_get_config`     | Dataclass models (Service, ServicePort, VnfProfile, etc.) | Uses `dataclasses.asdict()` |
| `Config`             | Alias for `_Serialisable`          | Backward compatibility             |

---

### Interfaces

All interfaces inherit from `Interface`. The `type` attribute identifies the interface kind and is excluded from JSON output.

#### Interface (base)

```python
Interface(name='', alias='', ip_addr='', owner_tag='',
          firewall_profile='', admin='', type='')
```

#### IpInterface

```python
IpInterface(name='ip-1', admin='up', l3shunt='disable')
# type = 'ip'
```

#### VPort

```python
VPort(
    name='vp-1',
    vlan_id=100,
    port_type='vhost',
    admin='up',
    dev_name='',          # defaults to name if empty
    domain='default',
    dequeue_shaper_rate=0,
    uplink_status_propagation='enable'
)
# type = 'vport'
```

#### GigabitEthernet

Unified class supporting two construction styles:

```python
# Style 1: individual arguments
ge = GigabitEthernet(
    name='ge-1/1',
    mtu=9600,
    speed=1000,
    lldp_da='nearest-bridge',
    lldp_mode='tx-and-rx',
    tun_lacp='enable',
)

# Style 2: pre-built dicts
ge = GigabitEthernet(
    name='ge-1/1',
    lldp={'da': 'nearest-bridge', 'mode': 'tx-and-rx'},
    tunnel={'lacp': 'enable', 'stp': 'disable'},
)

# GigabitEthernet1 is an alias
from adva_api import GigabitEthernet1
# GigabitEthernet1 is GigabitEthernet → True
```

When a dict is provided, it takes priority over individual arguments. When neither is provided, defaults are used.

**All GigabitEthernet parameters:**

| Parameter            | Default                | Description                    |
|----------------------|------------------------|--------------------------------|
| `name`               | `''`                   | Interface name                 |
| `admin`              | `'up'`                 | Administrative state           |
| `duplex`             | `'full'`               | Duplex mode                    |
| `auto_negotiation`   | `'enable'`             | Auto-negotiation               |
| `crossover`          | `'automatic'`          | MDI/MDIX crossover             |
| `speed`              | `1000`                 | Port speed (Mbps)              |
| `sr_iov`             | `'disable'`            | SR-IOV                         |
| `mtu`                | `9600`                 | Maximum transmission unit      |
| `master_slave`       | `'auto-prefer-slave'`  | Master/slave mode              |
| `output_rate`        | `'1000000000'`         | Output rate (bps)              |
| `attach`             | `'true'`               | Attach state                   |
| `reserved_mac`       | `'disable'`            | Reserved MAC                   |
| `oam`                | `'disable'`            | OAM                            |
| `oam_activity`       | `'active'`             | OAM activity mode              |
| `oam_loopback`       | `'enable'`             | OAM loopback                   |
| `lldp`               | `None` → built from args | LLDP config dict             |
| `tunnel`             | `None` → built from args | Tunnel protocol config dict  |
| `link_loss_forward`  | `[]`                   | Link loss forwarding targets   |

#### Aggregation

```python
agg = Aggregation(
    name='ag-1',
    lacp='enable',
    load_balance='srcdstmac',
    max_active_members=2,
    actor_system_priority=65535,
    members=[]
)
# Note: 'admin' is excluded from JSON output for aggregation interfaces
```

#### AggregationMember

```python
member = AggregationMember(
    name='ge-1/1',
    activity='active',
    actor_timeout='short',
    actor_port_priority=0,
    group_name='ag-1'
)
```

---

### Services

#### Service

```python
svc = Service(
    name='svc-1',
    type='e-lan',          # 'e-lan' | 'e-line' | ...
    fib_limit='65000',
    learning='enable',
    storm_control='1000',
    owner_tag='',
    domain='default',
    l4_port_range='49152-49183',
    serviceports=[]
)
```

#### ServicePort

`mode` and `vlan` are init-only parameters (`InitVar`) — they drive automatic configuration of `ingress`, `egress`, and `matchrules` but are never serialised to JSON.

VLAN match rule strings are available as class constants:

```python
ServicePort.UNTAGGED  # 'untagged * * * *'
ServicePort.TAGGED    # 'tagged * * * *'
ServicePort.TRUNK     # '* * * * *'
```

**Mode: `access`** — untagged port on a specific VLAN. Requires `vlan`.

```python
sp = ServicePort(name='sp-1', interface='vport-1', vlan=187)
# ingress:    "push 187 p-bit c-vlan-tpid passdei"
# egress:     "pop"
# matchrules: [{"name": "10", "rule": "untagged * * * *"}]
```

**Mode: `trunk`** — passes all traffic as-is (tagged and untagged).

```python
sp = ServicePort(name='sp-1', interface='vport-1', mode='trunk')
# ingress:    "fwd"
# egress:     "fwd"
# matchrules: [{"name": "10", "rule": "* * * * *"}]
```

**Mode: `tagged`** — passes only tagged traffic. Used as the tagged half of a native VLAN trunk.

```python
sp = ServicePort(name='sp-1', interface='vport-1', mode='tagged')
# ingress:    "fwd"
# egress:     "fwd"
# matchrules: [{"name": "10", "rule": "tagged * * * *"}]
```

**Mode: `native_vlan`** — untagged traffic treated as a specific VLAN. Semantically equivalent to `access` but expresses intent when paired with a `tagged` port.

```python
sp = ServicePort(name='sp-2', interface='vport-1', mode='native_vlan', vlan=100)
# ingress:    "push 100 p-bit c-vlan-tpid passdei"
# egress:     "pop"
# matchrules: [{"name": "10", "rule": "untagged * * * *"}]
```

**Mode: `trunk` / `tagged` with allowed VLANs** — equivalent to Cisco `switchport trunk allowed vlan`. Pass a comma-separated string of VLAN numbers; use a hyphen for ranges. Supported in both `trunk` and `tagged` modes.

```python
# одиночные VLANы
ServicePort(name='sp-1', interface='vport-1', mode='trunk', allowed_vlans='10,20,30')
# matchrules: [{"name":"10","rule":"10 * * *"}, {"name":"20","rule":"20 * * *"}, {"name":"30","rule":"30 * * *"}]

# диапазон
ServicePort(name='sp-1', interface='vport-1', mode='trunk', allowed_vlans='100-200')
# matchrules: [{"name":"10","rule":"100-200 * * *"}]

# смешанный
ServicePort(name='sp-1', interface='vport-1', mode='trunk', allowed_vlans='10,20,100-200')
# matchrules: [{"name":"10","rule":"10 * * *"}, {"name":"20","rule":"20 * * *"}, {"name":"30","rule":"100-200 * * *"}]

# транк с нативным VLANом + фильтрация на тегированном порту
sp_tagged = ServicePort(name='sp-1', interface='vport-1', mode='tagged', allowed_vlans='10,20,30')
sp_native = ServicePort(name='sp-2', interface='vport-1', mode='native_vlan', vlan=100)
```

---

**Trunk with native VLAN** — create two ports explicitly: one for tagged traffic, one for the native VLAN. Each port is configured independently and added to the service together.

```python
sp_tagged = ServicePort(name='sp-1', interface='vport-1', mode='tagged', owner_tag='John')
sp_native = ServicePort(name='sp-2', interface='vport-1', mode='native_vlan', vlan=100, owner_tag='John')

svc = Service(name='svc-1', type='e-lan', serviceports=[sp_tagged, sp_native])
```

**Explicit values always override mode defaults.** If `ingress`, `egress`, or `matchrules` are set explicitly, `mode` will not overwrite them:

```python
sp = ServicePort(
    name='sp-1', interface='vport-1', vlan=187,
    egress='fwd',                                       # overrides mode default 'pop'
    matchrules=[{'name': '5', 'rule': '100-200 * * *'}] # overrides mode default
)
# ingress:    "push 187 p-bit c-vlan-tpid passdei"  ← mode applied (was 'fwd')
# egress:     "fwd"                                  ← explicit, not overridden
# matchrules: [{"name": "5", "rule": "100-200 * * *"}] ← explicit, not overridden
```

---

### VNF

#### VnfProfile

```python
profile = VnfProfile(name='prof-1', vcpus=4, maxMem=2048, cpuExcl=1)
```

#### Vnf

Supports conditional attributes — fields like `vnfdef`, `secondary_disk`, and cloud-init parameters are only included in JSON if provided.

```python
vnf = Vnf(
    name='my-vnf',
    image='router.qcow2',
    profile='prof-1',
    admin='down',
    ethports=[],
    vnfdef='custom.xml',              # optional
    secondary_disk='data.qcow2',     # optional
    cloudinit_enable='enable',
    cloudinit_user_data='cloud.cfg',  # optional
)

cfg = vnf.get_config(jsn=False)
assert 'vnfdef' in cfg                     # ✓ provided
assert 'cloudinit-config-drive' not in cfg  # ✓ not provided
```

#### VnfPort

```python
port = VnfPort(
    name='vnfport-1',
    admin='up',
    mac='aa:bb:cc:dd:ee:ff',  # optional
    connection='vp-1',
    queues=4                   # only included if > 1
)
```

---

### Firewall

#### FirewallPort

Validates all fields on creation. Raises specific exceptions for invalid values.

```python
fp = FirewallPort(port="443", state="enable", protocol="tcp", direction="incoming")
```

| Parameter   | Allowed values                     |
|-------------|------------------------------------|
| `port`      | `1`–`65535` (as string)            |
| `state`     | `enable`, `disable`                |
| `protocol`  | `tcp`, `udp`, `all`                |
| `direction` | `incoming`                         |

Exceptions: `InvalidPortNumber`, `InvalidState`, `InvalidProtocol`, `InvalidDirection`.

#### FirewallProfile

```python
profile = FirewallProfile(
    name="fw-web",
    firewallports=[
        FirewallPort(port="80"),
        FirewallPort(port="443"),
    ]
)
```

---

### TACACS

#### TacacsServer

Validates IP addresses on creation. Raises `ValueError` for invalid IPs.

```python
server = TacacsServer(
    ip_server='10.0.0.100',
    ip_client='10.0.0.1',
    key='shared-secret',
    timeout='10'           # defaults to '5' if invalid
)
```

#### TacacsConfig

```python
config = TacacsConfig(
    authholder='tacacs,local',       # 'local' | 'local,tacacs' | 'tacacs,local' | 'tacacs'
    accounting_enable='enable',      # 'enable' | 'disable'
    tacacs_1=server1.get_config(jsn=False),
    tacacs_2=server2.get_config(jsn=False),
)
```

---

## Endpoint Registry (urn_data.py)

All API endpoints are declared in a single registry. Each entry maps a command name to an API path and HTTP method.

### Registered Commands

| Command                      | Method   | API Path                                         | Version |
|------------------------------|----------|--------------------------------------------------|---------|
| `get-token`                  | POST     | `/vse/api/v1.0/login`                            | v1      |
| `get-info`                   | GET      | `/vse/api/v1.0/info`                             | v1      |
| `get-config`                 | GET      | `/vse/api/v1.0/config/working`                   | v1      |
| `get-version`                | GET      | `/status`                                        | —       |
| `get-system-info`            | GET      | `/vse/api/v1.0/config/working/system/`           | v1      |
| `set-system-info`            | POST     | `/vse/api/v1.0/config/working/system/`           | v1      |
| `config-lock`                | POST     | `/vse/api/v1.0/config/lock/`                     | v1      |
| `config-unlock`              | POST     | `/vse/api/v1.0/config/unlock/`                   | v1      |
| `config-abandon`             | POST     | `/vse/api/v1.0/config/abandon/`                  | v1      |
| `config-commit`              | POST     | `/vse/api/v1.0/config/commit/`                   | v1      |
| `config-verify`              | POST     | `/vse/api/v1.0/config/commit/verify/`            | v1      |
| `get-config-commit`          | GET      | `/vse/api/v1.0/config/commit/`                   | v1      |
| `get-snmp`                   | GET      | `/vse/api/v1.0/config/active/snmp/v2`            | v1      |
| `get-services`               | GET      | `/vse/api/v1.0/config/active/services`           | v1      |
| `create-service`             | POST     | `/vse/api/v1.0/config/working/services/`         | v1      |
| `modify-service`             | PUT      | `/vse/api/v1.0/config/working/services/`         | v1      |
| `del-service`                | DELETE   | `/vse/api/v1.0/config/working/services`          | v1      |
| `get-interface-list`         | GET      | `/vse/api/v1.0/config/working/interfaces`        | v1      |
| `create-interface`           | POST     | `/vse/api/v1.0/config/working/interfaces`        | v1      |
| `delete-interface`           | DELETE   | `/vse/api/v1.0/config/working/interfaces`        | v1      |
| `config-gigabit-int`         | POST     | `/vse/api/v1.0/config/working/interfaces/gigabit`| v1      |
| `config-vport-int`           | POST     | `/vse/api/v1.0/config/working/interfaces/vport/` | v1      |
| `get-vnf-images`             | GET      | `/vse/api/v1.0/userfile/vnf-image`               | v1      |
| `upload-vnf-image`           | POST     | `/vse/api/v1.0/userfile/vnf-image`               | v1      |
| `delete-vnf-image`           | DELETE   | `/vse/api/v1.0/userfile/vnf-image`               | v1      |
| `get-vnf-list`               | GET      | `/vse/api/v1.0/config/working/virt/vnfs`         | v1      |
| `deploy-vnf`                 | POST     | `/vse/api/v3.0/config/working/virt/vnfs`         | v3      |
| `delete-vnf`                 | DELETE   | `/vse/api/v3.0/config/working/virt/vnfs`         | v3      |
| `get-vnf-profiles`           | GET      | `/vse/api/v3.0/config/working/virt/profiles`     | v3      |
| `configure-vnf-profiles`     | POST     | `/vse/api/v3.0/config/working/virt/profiles`     | v3      |
| `delete-vnf-profile`         | DELETE   | `/vse/api/v3.0/config/working/virt/profiles`     | v3      |
| `configure-firewall-profiles`| POST     | `/vse/api/v3.0/config/working/firewallprofiles`  | v3      |
| `delete-firewall-profiles`   | DELETE   | `/vse/api/v3.0/config/working/firewallprofiles`  | v3      |
| `get-tacacs`                 | GET      | `/vse/api/v3.0/config/working/system/tacacs-server/` | v3  |

### Adding New Endpoints

Edit the `_ENDPOINTS` dict in `urn_data.py`:

```python
from urn_data import _Endpoint, Method, _V1, _V3

# In the _ENDPOINTS dict:
"my-new-command": _Endpoint(f"{_V1}/config/working/new-resource", Method.POST),

# With fixed path (no argument appended):
"my-fixed-command": _Endpoint(f"{_V3}/some/fixed/path/", Method.GET, append_argument=False),
```

---

## Usage Examples

### Standalone Calls (auto-config)

Each call is its own transaction — no manual lock/commit needed:

```python
from adva_api import API, VPort, GigabitEthernet, Service

api = API(url="https://10.0.0.1", username="admin", password="admin")
api.get_token()

# Create interfaces — lock → create → commit (automatic)
api.configure_interface(VPort(name="vp-1", vlan_id=100))
api.configure_interface(GigabitEthernet(name="ge-1/1", mtu=9000))

# Create service
api.create_service(Service(name="svc-1", type="e-lan"))

# Delete
api.delete_service("svc-1")
api.delete_interface(VPort(name="vp-1"))
```

### Batch Operations

Pass a list to perform multiple operations in a single transaction:

```python
api.configure_interface([
    VPort(name="vp-1", vlan_id=100),
    VPort(name="vp-2", vlan_id=200),
    GigabitEthernet(name="ge-1/1", mtu=9000),
    GigabitEthernet(name="ge-1/2", mtu=9000),
])

api.delete_service(["svc-1", "svc-2", "svc-3"])
```

### Manual Transaction (mixed operations)

For combining different operation types in one transaction:

```python
api.lock_config()

api.configure_interface([ge1, ge2])
api.create_service(svc1)
api.delete_interface(old_vport)

api.config_commit()
```

### Firewall Configuration

```python
from adva_api import API, FirewallPort, FirewallProfile

api = API(url="https://10.0.0.1", username="admin", password="admin")
api.get_token()

fw = FirewallProfile(
    name="web-server",
    firewallports=[
        FirewallPort(port="80", protocol="tcp"),
        FirewallPort(port="443", protocol="tcp"),
        FirewallPort(port="22", protocol="tcp"),
    ]
)

api.query("configure-firewall-profiles", payload=fw.get_config())
```

### VNF Deployment

```python
from adva_api import API, VnfProfile

api = API(url="https://10.0.0.1", username="admin", password="admin")
api.get_token()

profile = VnfProfile(name="router-profile", vcpus=4, maxMem=4096)
api.create_vnf_profile(profile.get_config())

# Deploy image (blocks until complete)
api.deploy_image({"target-name": "router-image", "source": "tftp://..."})
```

### Emergency Config Abandon

```python
from adva_api import API

api = API(url="https://10.0.0.1", username="admin", password="admin")
api.config_abandon(emergency=True)  # reads token from token.toc
```

---

## HTTP Status Codes

The `return_code()` function maps status codes to human-readable messages:

| Code | Message                        |
|------|--------------------------------|
| 200  | OK                             |
| 204  | OK. No content                 |
| 400  | Bad request                    |
| 401  | Unauthorized                   |
| 403  | Forbidden                      |
| 404  | Not found                      |
| 405  | Method Not Allowed             |
| 409  | Conflict                       |
| 412  | Preliminary Verification Failed|

---

## Logging

The library uses Python's standard `logging` module.

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
```

Log levels used:

| Level     | Usage                                              |
|-----------|----------------------------------------------------|
| `INFO`    | Token received, config locked/committed, interface and service operations |
| `WARNING` | Token file write failure, config lock failure      |
| `ERROR`   | Auth failure, unlock failure                       |

---

## Migration from Original Code

### What Changed

| Change                           | Impact                                               |
|----------------------------------|------------------------------------------------------|
| `TacacsServer` raises on invalid IP | Add try/except around constructor                 |
| `delete_service` returns list for multiple items | Check return type if processing results |
| `retrying` dependency removed    | Remove from requirements                             |
| Module split into `models.py` + `adva_api.py` | `from adva_api import ...` still works     |

### What Works Without Changes

- `from adva_api import VPort, Service, API` — re-exports from models
- `api.query("command", argument="x")` — same signature
- `model.get_config()` — same JSON output format
- `GigabitEthernet1(...)` — alias for unified `GigabitEthernet`
- `Config` — alias for `_Serialisable` base class
- `Interface.type`, `Service.type` — original attribute names preserved
