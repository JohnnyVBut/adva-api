"""
ADVA API endpoint registry.

Provides a declarative mapping of command names to API endpoints.
The public function `get_urn_data(command, url, argument)` is the only
entry point consumed by connector_api.py — its signature is unchanged.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

class Method(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


_V1 = "/vse/api/v1.0"
_V3 = "/vse/api/v3.0"


# ---------------------------------------------------------------------------
#  Endpoint descriptor
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Endpoint:
    """Immutable descriptor for a single API endpoint."""
    path: str
    method: Method
    append_argument: bool = True   # whether `argument` is appended to the path


# ---------------------------------------------------------------------------
#  Endpoint registry  (created once at module load time)
# ---------------------------------------------------------------------------

_ENDPOINTS: dict[str, _Endpoint] = {

    # --- Authentication ----------------------------------------------------
    "get-token":                _Endpoint(f"{_V1}/login",                           Method.POST),

    # --- System / info -----------------------------------------------------
    "get-info":                 _Endpoint(f"{_V1}/info",                            Method.GET),
    "get-config":               _Endpoint(f"{_V1}/config/working",                  Method.GET),
    "get-version":              _Endpoint("/status",                                Method.GET),
    "get-system-info":          _Endpoint(f"{_V1}/config/working/system/",          Method.GET,     append_argument=False),
    "set-system-info":          _Endpoint(f"{_V1}/config/working/system/",          Method.POST,    append_argument=False),

    # --- Configuration lock / commit / abandon -----------------------------
    "config-lock":              _Endpoint(f"{_V1}/config/lock/",                    Method.POST,    append_argument=False),
    "config-unlock":            _Endpoint(f"{_V1}/config/unlock/",                  Method.POST,    append_argument=False),
    "config-abandon":           _Endpoint(f"{_V1}/config/abandon/",                 Method.POST,    append_argument=False),
    "config-commit":            _Endpoint(f"{_V1}/config/commit/",                  Method.POST,    append_argument=False),
    "config-verify":            _Endpoint(f"{_V1}/config/commit/verify/",           Method.POST,    append_argument=False),
    "get-config-commit":        _Endpoint(f"{_V1}/config/commit/",                  Method.GET,     append_argument=False),

    # --- SNMP --------------------------------------------------------------
    "get-snmp":                 _Endpoint(f"{_V1}/config/active/snmp/v2",           Method.GET),

    # --- Services ----------------------------------------------------------
    "get-services":             _Endpoint(f"{_V1}/config/active/services",          Method.GET),
    "create-service":           _Endpoint(f"{_V1}/config/working/services/",        Method.POST),
    "modify-service":           _Endpoint(f"{_V1}/config/working/services/",        Method.PUT),
    "del-service":              _Endpoint(f"{_V1}/config/working/services",         Method.DELETE),

    # --- Interfaces --------------------------------------------------------
    "get-interface-list":       _Endpoint(f"{_V1}/config/working/interfaces",       Method.GET),
    "create-interface":         _Endpoint(f"{_V1}/config/working/interfaces",       Method.POST),
    "delete-interface":         _Endpoint(f"{_V1}/config/working/interfaces",       Method.DELETE),
    "config-gigabit-int":       _Endpoint(f"{_V1}/config/working/interfaces/gigabit", Method.POST),
    "config-vport-int":         _Endpoint(f"{_V1}/config/working/interfaces/vport/",  Method.POST),

    # --- VNF images --------------------------------------------------------
    "get-vnf-images":           _Endpoint(f"{_V1}/userfile/vnf-image",              Method.GET),
    "upload-vnf-image":         _Endpoint(f"{_V1}/userfile/vnf-image",              Method.POST),
    "delete-vnf-image":         _Endpoint(f"{_V1}/userfile/vnf-image",              Method.DELETE),

    # --- VNF management (v3) -----------------------------------------------
    "get-vnf-list":             _Endpoint(f"{_V1}/config/working/virt/vnfs",        Method.GET),
    "deploy-vnf":               _Endpoint(f"{_V3}/config/working/virt/vnfs",        Method.POST,    append_argument=False),
    "delete-vnf":               _Endpoint(f"{_V3}/config/working/virt/vnfs",        Method.DELETE),

    # --- VNF profiles (v3) -------------------------------------------------
    "get-vnf-profiles":         _Endpoint(f"{_V3}/config/working/virt/profiles",    Method.GET,     append_argument=False),
    "configure-vnf-profiles":   _Endpoint(f"{_V3}/config/working/virt/profiles",    Method.POST,    append_argument=False),
    "delete-vnf-profile":       _Endpoint(f"{_V3}/config/working/virt/profiles",    Method.DELETE),

    # --- Firewall profiles (v3) --------------------------------------------
    "configure-firewall-profiles": _Endpoint(f"{_V3}/config/working/firewallprofiles", Method.POST, append_argument=False),
    "delete-firewall-profiles":    _Endpoint(f"{_V3}/config/working/firewallprofiles", Method.DELETE),

    # --- TACACS (v3) -------------------------------------------------------
    "get-tacacs":               _Endpoint(f"{_V3}/config/working/system/tacacs-server/", Method.GET, append_argument=False),

    # --- Testing only ------------------------------------------------------
    "wrong-method":             _Endpoint(f"{_V1}/login",                           Method.GET),
}


# ---------------------------------------------------------------------------
#  Public API  (signature kept for backward compatibility)
# ---------------------------------------------------------------------------

def get_urn_data(command: str, url: str, argument: str = "/") -> Tuple[str, str]:
    """
    Resolve *command* to a full URL and HTTP method string.

    Parameters
    ----------
    command : str
        Logical command name (must exist in the endpoint registry).
    url : str
        Base URL of the ADVA appliance, e.g. ``https://10.0.0.1``.
    argument : str, optional
        Path suffix to append (e.g. ``/gigabit`` or ``/my-service``).
        Defaults to ``"/"``.

    Returns
    -------
    tuple[str, str]
        ``(full_url, http_method)``

    Raises
    ------
    ValueError
        If *command* is not found in the registry.
    """
    endpoint = _ENDPOINTS.get(command)
    if endpoint is None:
        raise ValueError(
            f"Unknown command: '{command}'. "
            f"Available commands: {', '.join(sorted(_ENDPOINTS))}"
        )

    if endpoint.append_argument:
        full_url = f"{url}{endpoint.path}{argument}"
    else:
        full_url = f"{url}{endpoint.path}"

    return full_url, str(endpoint.method.value)
