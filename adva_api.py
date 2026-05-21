"""
ADVA Ensemble Connector REST API client.

API client with session-based HTTP transport and automatic retry.
Data models are defined in :mod:`models` and re-exported here
for backward compatibility.
"""

import logging
import time
import json
import os
import stat
from functools import wraps

import requests
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth

import urn_data as ud

# Re-export all models so existing ``from adva_api import VPort, Service``
# continues to work without changes.
from models import (                                        # noqa: F401
    # utilities
    is_valid_ip, response_format, get_short_list,
    # serialisation base
    Config, _Serialisable,
    # interfaces
    Interface, IpInterface, VPort,
    GigabitEthernet, GigabitEthernet1, Aggregation,
    AggregationMember,
    # services
    Service, ServicePort,
    # VNF
    VnfProfile, Vnf, VnfPort,
    # firewall
    InvalidPortNumber, InvalidState, InvalidDirection, InvalidProtocol,
    FirewallPort, FirewallProfile,
    # TACACS
    TacacsServer, TacacsConfig,
)

urllib3.disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#  Status codes
# ---------------------------------------------------------------------------

_STATUS_MESSAGES = {
    200: "OK",
    204: "OK. No content",
    400: "Bad request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not found",
    405: "Method Not Allowed",
    409: "Conflict",
    412: "Preliminary Verification Failed",
}


def return_code(code: int) -> str:
    return _STATUS_MESSAGES.get(code, f"Unknown status {code}")


# ---------------------------------------------------------------------------
#  HTTP session factory
# ---------------------------------------------------------------------------

def _create_session(
    username: str,
    password: str,
    timeout: int = 10,
    max_retries: int = 3,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """
    Create a pre-configured requests.Session with:
      - Basic auth
      - TLS verification disabled (self-signed certs on appliances)
      - Automatic retry with exponential backoff
    """
    session = requests.Session()
    session.verify = False
    session.auth = HTTPBasicAuth(username, password)
    session.headers.update({"Content-Type": "application/json"})

    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "PUT", "DELETE"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.request_timeout = timeout  # type: ignore[attr-defined]
    return session


# ---------------------------------------------------------------------------
#  Auto-config decorator
# ---------------------------------------------------------------------------

def _auto_config(func):
    """
    If config is already locked (external transaction), just execute.
    Otherwise: lock → execute → commit (or abandon on error).
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.config_is_locked:
            return func(self, *args, **kwargs)
        self.lock_config()
        try:
            result = func(self, *args, **kwargs)
            self.config_commit()
            return result
        except Exception:
            self.config_abandon()
            raise
    return wrapper


# ===========================================================================
#  API client
# ===========================================================================

class API:
    """
    ADVA Ensemble Connector REST API client.

    Uses a persistent ``requests.Session`` with automatic retry
    instead of creating a new connection per request.
    """

    TOKEN_FILE = "token.toc"

    def __init__(self, url: str, username: str, password: str, token: str = ""):
        self.url = url
        self.username = username
        self.password = password
        self.token = token
        self.config_is_locked = False

        self._session = _create_session(username, password)

    # ------------------------------------------------------------------
    #  Low-level transport
    # ------------------------------------------------------------------

    def _request(self, method: str, uri: str, payload: str = "") -> tuple[int, str]:
        timeout = self._session.request_timeout  # type: ignore[attr-defined]
        headers = {"X-Auth-Token": self.token}

        response = self._session.request(
            method=method,
            url=uri,
            data=payload or None,
            headers=headers,
            timeout=timeout,
        )

        if response.status_code == 204:
            return 204, "No content"

        return response.status_code, response.text

    def query(self, command: str, argument: str = "", payload: str = "") -> tuple[int, str]:
        data = f"/{argument}" if argument else "/"
        uri, method = ud.get_urn_data(command, self.url, data)
        return self._request(method, uri, payload)

    # ------------------------------------------------------------------
    #  Authentication
    # ------------------------------------------------------------------

    def get_token(self) -> str:
        logger.info("Requesting auth token...")
        code, body = self.query(
            "get-token",
            payload=json.dumps({"username": self.username, "password": self.password}),
        )

        if code != 200:
            logger.error(f"Auth failed: {code} {return_code(code)}")
            raise EnvironmentError(f"Authentication failed with code {code}")

        self.token = json.loads(body)["token"]
        logger.info("Session token received")

        try:
            with open(self.TOKEN_FILE, "w", encoding="utf8") as fh:
                fh.write(self.token)
            os.chmod(self.TOKEN_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as exc:
            logger.warning(f"Cannot write token file {self.TOKEN_FILE}: {exc}")

        return self.token

    # ------------------------------------------------------------------
    #  VNF images
    # ------------------------------------------------------------------

    def get_image_list(self, brief: bool = False):
        code, result = self.query("get-vnf-images")
        out = json.loads(result)
        if brief:
            return get_short_list(out["vnf-image"], "name")
        return out

    def upload_vnf_image(self, payload=None):
        if payload:
            return self.query("upload-vnf-image", payload=payload)
        return None, "Missing payload"

    def delete_vnf_image(self, image_name: str):
        code, result = self.query("delete-vnf-image", argument=image_name)
        logger.info(f"delete_vnf_image {image_name}: {code} {return_code(code)}")
        return result

    def get_image_status(self, image_name: str) -> str | None:
        for image in self.get_image_list()["vnf-image"]:
            if image["name"] == image_name:
                return image["status"]
        return None

    def deploy_image(self, image_config: dict) -> str:
        self.upload_vnf_image(image_config)
        target = image_config["target-name"]
        while True:
            status = self.get_image_status(target)
            if status == "complete":
                return f"{target}: {status}"
            logger.info(f"deploy_image {target}: {status}")
            time.sleep(5)

    # ------------------------------------------------------------------
    #  Services
    # ------------------------------------------------------------------

    def get_services_list(self, brief: bool = True):
        code, result = self.query("get-services")
        logger.info(f"get_services: {code} {return_code(code)}")
        out = json.loads(result)
        if brief:
            return get_short_list(out, "name")
        return out

    @_auto_config
    def create_service(self, config: Service | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(config, list):
            config = [config]

        results = []
        for svc in config:
            if not isinstance(svc, Service):
                raise TypeError(f"Expected Service, got {type(svc).__name__}")
            result = self.query("create-service", argument=svc.name,
                                payload=svc.get_config())
            logger.info(f"create_service {svc.name}: {result[0]} {return_code(result[0])}")
            results.append(result)

        return results if len(results) > 1 else results[0]

    @_auto_config
    def modify_service(self, config: Service | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(config, list):
            config = [config]

        results = []
        for svc in config:
            if not isinstance(svc, Service):
                raise TypeError(f"Expected Service, got {type(svc).__name__}")
            result = self.query("modify-service", argument=svc.name,
                                payload=svc.get_config())
            logger.info(f"modify_service {svc.name}: {result[0]} {return_code(result[0])}")
            results.append(result)

        return results if len(results) > 1 else results[0]

    @_auto_config
    def delete_service(self, services: str | Service | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(services, list):
            services = [services]

        results = []
        for svc in services:
            name = svc.name if isinstance(svc, Service) else svc
            result = self.query(command="del-service", argument=name)
            logger.info(f"Deleting service {name} — code {result[0]}")
            results.append(result)

        return results if len(results) > 1 else results[0]

    # ------------------------------------------------------------------
    #  VNFs
    # ------------------------------------------------------------------

    def get_vnf_list(self, brief: bool = False):
        code, result = self.query("get-vnf-list")
        out = json.loads(result)
        logger.info(f"get_vnf_list: {code} {return_code(code)}")
        if brief:
            return get_short_list(out, "name")
        return out

    @_auto_config
    def create_vnf_profile(self, payload: str):
        return self.query("configure-vnf-profiles", payload=payload)

    def get_vnf_state(self, name: str) -> str:
        vnf_states = json.loads(self.query(command='get-vnf-info')[1])
        vnf_state = next((x for x in vnf_states if x["name"] == name), None)
        if vnf_state is None:
            raise ValueError(f"VNF '{name}' not found")
        return vnf_state['state']

    def get_vnf_config(self, name: str) -> dict:
        vnf_configs = self.get_vnf_list()
        vnf_config = next((x for x in vnf_configs if x["name"] == name), None)
        if vnf_config is None:
            raise ValueError(f"VNF '{name}' not found")
        return vnf_config

    def get_vnf_object_by_name(self, name: str) -> Vnf:
        vnf_config = self.get_vnf_config(name)
        config = {
            k.replace('-', '_'): v
            for k, v in vnf_config.items()
        }
        return Vnf(**config)

    @_auto_config
    def shutdown_vnf(self, vnf: Vnf):
        if not isinstance(vnf, Vnf):
            raise TypeError(f"Expected Vnf, got {type(vnf).__name__}")
        vm_state = self.get_vnf_state(vnf.name)
        if vm_state == 'running':
            vnf.admin = 'down'
            result = self.query('modify-vnf', payload=vnf.get_config())
            logger.info(f"Trying to shut down VNF {vnf.name}: {result[0]} {return_code(result[0])}")
            for i in range(0, 21):
                if self.get_vnf_state(vnf.name) != 'shutdown':
                    time.sleep(3)
                logger.info(f"VNF {vnf.name} is now in a SHUTDOWN state")
                break
            return True
        # possible vm states are: 'running','shutdown','crashed','restoring','unknown'
        else:
            logger.info(f"VNF {vnf.name} is in {vm_state} state")
            return True

    @_auto_config
    def config_vnf(self, config: Vnf | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(config, list):
            config = [config]
        results = []
        for vnf in config:
            if not isinstance(vnf, Vnf):
                raise TypeError(f"Expected Vnf, got {type(vnf).__name__}")
            if vnf.name not in self.get_vnf_list(brief=True):
                operation = 'deploy-vnf'
            else:
                operation = 'modify-vnf'
                logger.info(f"VNF {vnf.name} is already deployed and will be modified. This requires a VM shutdown")
            if operation == 'modify-vnf':
                self.shutdown_vnf(vnf)
            result = self.query(operation, payload=vnf.get_config())
            logger.info(f"{operation} VNF {vnf.name}: {result[0]} {return_code(result[0])}")
            results.append(result)
        return results if len(results) > 1 else results[0]

    # ------------------------------------------------------------------
    #  Interfaces
    # ------------------------------------------------------------------

    @_auto_config
    def configure_interface(self, config: Interface | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(config, list):
            config = [config]

        results = []
        for iface in config:
            if not isinstance(iface, Interface):
                raise TypeError(f"Expected Interface subclass, got {type(iface).__name__}")
            result = self.query("create-interface", argument=iface.type,
                                payload=iface.get_config())
            logger.info(f"configure_interface {iface.name} ({iface.type}): {result[0]} {return_code(result[0])}")
            results.append(result)

        return results if len(results) > 1 else results[0]

    @_auto_config
    def delete_interface(self, config: Interface | list) -> list[tuple[int, str]] | tuple[int, str]:
        if not isinstance(config, list):
            config = [config]

        results = []
        for iface in config:
            if not isinstance(iface, Interface):
                raise TypeError(f"Expected Interface subclass, got {type(iface).__name__}")
            argument = f"{iface.type}/{iface.name}"
            logger.info(f"Deleting interface {iface.name} (type {iface.type})")
            result = self.query(command="delete-interface", argument=argument)
            results.append(result)

        return results if len(results) > 1 else results[0]

    # ------------------------------------------------------------------
    #  Configuration management
    # ------------------------------------------------------------------

    def lock_config(self) -> tuple[int, str]:
        logger.info("Locking config...")
        code, result = self.query("config-lock")
        self.config_is_locked = code == 200
        if self.config_is_locked:
            logger.info("Config locked")
        return code, result

    def config_locked(self, force: bool = False) -> bool:
        if force:
            if not self.config_is_locked:
                code, result = self.lock_config()
                if code == 200:
                    self.config_is_locked = True
                    return True
                else:
                    self.config_is_locked = False
                    logger.warning(f"Failed to lock config: {code} {result}")
                    return False
            else:
                return False
        return self.config_is_locked

    def config_unlock(self) -> int:
        if not self.config_is_locked:
            logger.info("Config is not locked")
            return 200

        code, result = self.query("config-unlock")
        if code == 200:
            logger.info("Config unlocked")
            self.config_is_locked = False
        else:
            logger.error(f"Unable to unlock config: {code}")
        return code

    def config_abandon(self, emergency: bool = False):
        if not emergency:
            return self.query(command="config-abandon")

        try:
            with open(self.TOKEN_FILE, "r", encoding="utf8") as fh:
                self.token = fh.read().strip()
            return self.query(command="config-abandon")
        except OSError as exc:
            logger.error(f"Cannot read token file {self.TOKEN_FILE}: {exc}")
            return None

    def config_commit(self) -> tuple[int, str]:
        logger.info("Committing configuration")
        code, result = self.query("config-commit")
        logger.info(f"config_commit: {code} {result}")
        return code, result

    # ------------------------------------------------------------------
    #  Testing helper
    # ------------------------------------------------------------------

    def get_wrong(self):
        self.query("wrong-method")
        return None
