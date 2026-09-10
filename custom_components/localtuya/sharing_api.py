"""Tuya Device Sharing API adapter for LocalTuya.

This uses the same QR login mechanism as Home Assistant's official Tuya
integration.  It intentionally exposes a small compatibility surface matching
what LocalTuya already expects from its legacy cloud API: ``device_list`` and
``async_get_devices_list``.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from tuya_sharing import Manager

_LOGGER = logging.getLogger(__name__)

TUYA_CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
TUYA_SCHEMA = "haauthorize"

TOKEN_FIELDS = ("t", "uid", "expire_time", "access_token", "refresh_token")


class _TokenSaver:
    """Receive refreshed tokens from tuya-device-sharing-sdk."""

    def __init__(self, token_info: dict[str, Any]) -> None:
        self.token_info = dict(token_info)

    def update_token(self, token_info: dict[str, Any]) -> None:
        self.token_info = {key: token_info.get(key) for key in TOKEN_FIELDS}


def _plain(value: Any) -> Any:
    """Convert SDK namespaces and int-keyed dictionaries to JSON-safe values."""
    if isinstance(value, SimpleNamespace):
        value = vars(value)
    if isinstance(value, dict):
        return {str(key): _plain(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(val) for val in value]
    return value


def _device_to_dict(device: Any) -> dict[str, Any]:
    """Return every public field the SDK exposed for a device."""
    data: dict[str, Any] = {}
    for key, value in vars(device).items():
        if not key.startswith("_"):
            data[key] = _plain(value)
    return data


class TuyaSharingApi:
    """Adapter around tuya-device-sharing-sdk Manager."""

    def __init__(
        self,
        hass,
        user_code: str,
        terminal_id: str,
        endpoint: str,
        token_info: dict[str, Any],
        config_entry=None,
    ) -> None:
        self._hass = hass
        self._user_code = user_code
        self._terminal_id = terminal_id
        self._endpoint = endpoint
        self._token_saver = _TokenSaver(token_info)
        self._config_entry = config_entry
        self.device_list: dict[str, dict[str, Any]] = {}
        self.device_specs: dict[str, dict[str, Any]] = {}
        self._manager: Manager | None = None

    def _build_manager(self) -> Manager:
        return Manager(
            TUYA_CLIENT_ID,
            self._user_code,
            self._terminal_id,
            self._endpoint,
            self._token_saver.token_info,
            self._token_saver,
        )

    def _refresh_devices_sync(self) -> dict[str, dict[str, Any]]:
        if self._manager is None:
            self._manager = self._build_manager()
        self._manager.update_device_cache()
        return {
            str(device_id): _device_to_dict(device)
            for device_id, device in self._manager.device_map.items()
        }

    async def async_get_devices_list(self) -> str:
        """Refresh devices and persist any token refresh into the config entry."""
        try:
            devices = await self._hass.async_add_executor_job(self._refresh_devices_sync)
        except Exception as ex:  # SDK raises requests/manager exceptions directly
            _LOGGER.error("Device Sharing device list failed: %s", ex)
            return f"Device Sharing request failed: {ex}"

        self.device_list = devices
        await self._async_persist_refreshed_token()
        _LOGGER.info("Device Sharing loaded %d Tuya devices.", len(devices))
        return "ok"

    async def _async_persist_refreshed_token(self) -> None:
        if self._config_entry is None:
            return
        from .const import CONF_TOKEN_INFO

        old = self._config_entry.data.get(CONF_TOKEN_INFO, {})
        new = self._token_saver.token_info
        if old == new:
            return
        data = self._config_entry.data.copy()
        data[CONF_TOKEN_INFO] = dict(new)
        self._hass.config_entries.async_update_entry(self._config_entry, data=data)

    async def async_get_device_specifications(self, device_id: str):
        """Return specification-like data already included by Device Sharing.

        ``local_strategy`` is especially useful because it contains the local DP
        number together with the Tuya status code.
        """
        device = self.device_list.get(device_id)
        if not device:
            return None, "device not found"

        spec = {
            "category": device.get("category"),
            "function": device.get("function") or {},
            "status_range": device.get("status_range") or {},
            "local_strategy": device.get("local_strategy") or {},
        }
        self.device_specs[device_id] = spec

        safe = {
            "category": spec["category"],
            "function_codes": sorted(spec["function"].keys()),
            "status_codes": sorted(spec["status_range"].keys()),
            "local_dp_map": {
                str(dp): value.get("status_code")
                for dp, value in spec["local_strategy"].items()
                if isinstance(value, dict)
            },
        }
        _LOGGER.debug("Device Sharing DP metadata loaded: %s", safe)
        return spec, "ok"
