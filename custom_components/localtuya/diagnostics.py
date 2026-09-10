"""Privacy-safe diagnostics support for LocalTuya."""
from __future__ import annotations

import copy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_DEVICES, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .auto_config import auto_config_support_matrix
from .const import (
    CONF_ENDPOINT,
    CONF_LOCAL_KEY,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    CONF_USER_ID,
    DATA_CLOUD,
    DOMAIN,
)

CLOUD_DEVICES = "cloud_devices"
DEVICE_CONFIG = "device_config"
DEVICE_CLOUD_INFO = "device_cloud_info"
AUTO_CONFIG_SUPPORT = "auto_config_support"
REDACTED = "**REDACTED**"

# Keys that are credentials, stable account/device identifiers, or network
# identifiers. Product/category/status metadata intentionally remains visible so
# community issue reports can be useful without exposing secrets.
_SENSITIVE_KEYS = {
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_LOCAL_KEY,
    CONF_USER_ID,
    CONF_USER_CODE,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_HOST,
    "access_token",
    "refresh_token",
    "accesstoken",
    "refreshtoken",
    "token",
    "t",
    "uid",
    "uuid",
    "id",
    "device_id",
    "deviceid",
    "dev_id",
    "devid",
    "gw_id",
    "gwid",
    "localkey",
    "userid",
    "usercode",
    "terminalid",
    "clientid",
    "clientsecret",
    "ip",
}


def _sanitize(value: Any) -> Any:
    """Recursively redact credentials and unique/network identifiers."""
    if isinstance(value, dict):
        sanitized: dict[Any, Any] = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_KEYS:
                sanitized[key] = REDACTED
            else:
                sanitized[key] = _sanitize(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize(item) for item in value)
    return value


def _sanitize_device_mapping(devices: Any) -> Any:
    """Redact device IDs used as mapping keys while preserving device metadata."""
    if not isinstance(devices, dict):
        return _sanitize(devices)
    return {
        f"device_{index}": _sanitize(device)
        for index, (_device_id, device) in enumerate(devices.items(), start=1)
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a config entry."""
    data = _sanitize(copy.deepcopy(dict(entry.data)))
    if CONF_DEVICES in entry.data:
        data[CONF_DEVICES] = _sanitize_device_mapping(entry.data[CONF_DEVICES])

    cloud_api = hass.data.get(DOMAIN, {}).get(DATA_CLOUD)
    if cloud_api is not None:
        data[CLOUD_DEVICES] = _sanitize_device_mapping(
            copy.deepcopy(getattr(cloud_api, "device_list", {}))
        )

    data[AUTO_CONFIG_SUPPORT] = auto_config_support_matrix()
    return data


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return privacy-safe diagnostics for a single device.

    Semantic Tuya metadata and numeric DP mappings are intentionally retained;
    local keys, QR tokens, account/device identifiers and IP addresses are not.
    """
    data: dict[str, Any] = {AUTO_CONFIG_SUPPORT: auto_config_support_matrix()}
    dev_id = list(device.identifiers)[0][1].split("_")[-1]

    device_config = entry.data.get(CONF_DEVICES, {}).get(dev_id)
    if device_config is not None:
        data[DEVICE_CONFIG] = _sanitize(copy.deepcopy(device_config))

    cloud_api = hass.data.get(DOMAIN, {}).get(DATA_CLOUD)
    cloud_devices = getattr(cloud_api, "device_list", {}) if cloud_api is not None else {}
    if dev_id in cloud_devices:
        data[DEVICE_CLOUD_INFO] = _sanitize(copy.deepcopy(cloud_devices[dev_id]))

    return data
