"""Capability-based automatic entity configuration for LocalTuya.

The mapper intentionally uses Tuya semantic status codes rather than brands,
product IDs, or hard-coded DP numbers. Numeric DP IDs come from
``local_strategy`` (Device Sharing) or cloud specification metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from typing import Any

from homeassistant.const import (
    CONF_BRIGHTNESS,
    CONF_COLOR_TEMP,
    CONF_DEVICE_CLASS,
    CONF_FRIENDLY_NAME,
    CONF_ID,
    CONF_PLATFORM,
    CONF_SCENE,
    CONF_TEMPERATURE_UNIT,
    CONF_UNIT_OF_MEASUREMENT,
)

from .const import (
    CONF_BRIGHTNESS_LOWER,
    CONF_BRIGHTNESS_UPPER,
    CONF_BATTERY_DP,
    CONF_CLEAN_AREA_DP,
    CONF_CLEAN_RECORD_DP,
    CONF_CLEAN_TIME_DP,
    CONF_COLOR,
    CONF_COLOR_MODE,
    CONF_COMMANDS_SET,
    CONF_CURRENT_POSITION_DP,
    CONF_CURRENT_TEMPERATURE_DP,
    CONF_DOCKED_STATUS_VALUE,
    CONF_ENTITY_REGISTRY_ENABLED_DEFAULT,
    CONF_FAN_DIRECTION,
    CONF_FAN_DIRECTION_FWD,
    CONF_FAN_DIRECTION_REV,
    CONF_FAN_DPS_TYPE,
    CONF_FAN_ORDERED_LIST,
    CONF_FAN_OSCILLATING_CONTROL,
    CONF_FAN_SPEED_CONTROL,
    CONF_FAN_SPEED_MAX,
    CONF_FAN_SPEED_MIN,
    CONF_FAN_SPEED_DP,
    CONF_FAN_SPEEDS,
    CONF_FAULT_DP,
    CONF_HEURISTIC_ACTION,
    CONF_HVAC_MODE_DP,
    CONF_HVAC_MODE_SET,
    CONF_IDLE_STATUS_VALUE,
    CONF_LOCATE_DP,
    CONF_MAX_VALUE,
    CONF_MIN_VALUE,
    CONF_MODE_DP,
    CONF_MODES,
    CONF_OPTIONS,
    CONF_PASSIVE_ENTITY,
    CONF_PAUSED_STATE,
    CONF_POSITIONING_MODE,
    CONF_POSITION_INVERTED,
    CONF_POWERGO_DP,
    CONF_PRECISION,
    CONF_RESTORE_ON_RECONNECT,
    CONF_RETURN_MODE,
    CONF_RETURNING_STATUS_VALUE,
    CONF_SCALING,
    CONF_SET_POSITION_DP,
    CONF_STEPSIZE_VALUE,
    CONF_STOP_STATUS,
    CONF_TARGET_PRECISION,
    CONF_TARGET_TEMPERATURE_DP,
    CONF_TEMPERATURE_STEP,
    CONF_TEMP_MAX,
    CONF_TEMP_MIN,
    CONF_TRANSLATION_KEY,
)

_LOGGER = logging.getLogger(__name__)

SUPPORT_VALIDATED = "validated"
SUPPORT_IMPLEMENTED = "implemented"
SUPPORT_EXPERIMENTAL = "experimental"

# Public support matrix used by diagnostics and release documentation.  "validated"
# means exercised on real hardware during this fork's development.  "implemented"
# means the generic rule is active but has not yet been hardware-validated.
# Complex device families are deliberately created disabled-by-default until
# community hardware reports confirm their semantics.
AUTO_CONFIG_SUPPORT: dict[str, dict[str, str]] = {
    "socket_switch": {"level": SUPPORT_VALIDATED, "platform": "switch"},
    "electrical_telemetry": {"level": SUPPORT_VALIDATED, "platform": "sensor"},
    "light_rgb_cct": {"level": SUPPORT_VALIDATED, "platform": "light"},
    "generic_enum": {"level": SUPPORT_VALIDATED, "platform": "select"},
    "generic_number": {"level": SUPPORT_VALIDATED, "platform": "number"},
    "generic_readonly_boolean": {"level": SUPPORT_IMPLEMENTED, "platform": "binary_sensor"},
    "cover": {"level": SUPPORT_EXPERIMENTAL, "platform": "cover"},
    "fan": {"level": SUPPORT_EXPERIMENTAL, "platform": "fan"},
    "climate": {"level": SUPPORT_EXPERIMENTAL, "platform": "climate"},
    "vacuum": {"level": SUPPORT_EXPERIMENTAL, "platform": "vacuum"},
}


def auto_config_support_matrix() -> dict[str, dict[str, str]]:
    """Return a copy of the public auto-config support matrix."""
    return {key: value.copy() for key, value in AUTO_CONFIG_SUPPORT.items()}



@dataclass(slots=True)
class AutoConfigReport:
    """Result of capability analysis without exposing sensitive device data."""

    entities: list[dict[str, Any]] = field(default_factory=list)
    mapped_codes: list[str] = field(default_factory=list)
    ignored_codes: list[str] = field(default_factory=list)
    missing_local_dps: list[str] = field(default_factory=list)
    rejected_codes: list[str] = field(default_factory=list)


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _metadata_by_code(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Combine metadata from all SDK/API representations we currently support."""
    metadata: dict[str, dict[str, Any]] = {}
    for section_name in ("status_range", "function"):
        section = spec.get(section_name) or {}
        if isinstance(section, dict):
            for key, item in section.items():
                if not isinstance(item, dict):
                    continue
                code = item.get("code") or key
                metadata.setdefault(str(code), {}).update(item)
        elif isinstance(section, list):
            for item in section:
                if isinstance(item, dict) and item.get("code"):
                    metadata.setdefault(str(item["code"]), {}).update(item)

    # Device Sharing local_strategy can still describe type/range when the
    # function/status_range blocks are incomplete for a device.
    strategy = spec.get("local_strategy") or {}
    if isinstance(strategy, dict):
        for item in strategy.values():
            if not isinstance(item, dict) or not item.get("status_code"):
                continue
            code = str(item["status_code"])
            config = item.get("config_item") or {}
            if not isinstance(config, dict):
                continue
            target = metadata.setdefault(code, {})
            target.setdefault("code", code)
            if config.get("valueType"):
                target.setdefault("type", config["valueType"])
            if config.get("valueDesc") is not None:
                target.setdefault("values", config["valueDesc"])
    return metadata


def _dp_code_map(spec: dict[str, Any]) -> dict[str, int]:
    """Return semantic Tuya status code -> local numeric DP ID."""
    result: dict[str, int] = {}

    strategy = spec.get("local_strategy") or {}
    if isinstance(strategy, dict):
        for dp, item in strategy.items():
            if not isinstance(item, dict) or not item.get("status_code"):
                continue
            try:
                result[str(item["status_code"])] = int(dp)
            except (TypeError, ValueError):
                continue

    # Legacy Tuya cloud specification fallback.
    for section_name in ("functions", "status"):
        section = spec.get(section_name) or []
        if not isinstance(section, list):
            continue
        for item in section:
            if not isinstance(item, dict) or not item.get("code"):
                continue
            dp = item.get("dp_id", item.get("dpId"))
            try:
                result.setdefault(str(item["code"]), int(dp))
            except (TypeError, ValueError):
                continue

    return result




def _function_codes(spec: dict[str, Any]) -> set[str]:
    """Return semantic codes exposed as writable functions by Tuya."""
    result: set[str] = set()
    section = spec.get("function") or spec.get("functions") or {}
    if isinstance(section, dict):
        for key, item in section.items():
            if isinstance(item, dict):
                result.add(str(item.get("code") or key))
    elif isinstance(section, list):
        for item in section:
            if isinstance(item, dict) and item.get("code"):
                result.add(str(item["code"]))
    return result


def _values_for(code: str, metadata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return _json_dict(metadata.get(code, {}).get("values"))


def _friendly_code_name(code: str) -> str:
    """Make a conservative human-readable name from a Tuya semantic code."""
    aliases = {
        "countdown_1": "Countdown",
        "relay_status": "Power-on state",
        "light_mode": "Indicator mode",
    }
    if code in aliases:
        return aliases[code]
    return code.replace("_", " ").strip().title()


def _scale_for(code: str, metadata: dict[str, dict[str, Any]]) -> float | None:
    values = _json_dict(metadata.get(code, {}).get("values"))
    scale = values.get("scale")
    if scale is None:
        return None
    try:
        return 10 ** (-int(scale))
    except (TypeError, ValueError):
        return None


def _range_for(code: str, metadata: dict[str, dict[str, Any]]) -> tuple[int | None, int | None]:
    values = _json_dict(metadata.get(code, {}).get("values"))
    try:
        minimum = int(values["min"]) if "min" in values else None
        maximum = int(values["max"]) if "max" in values else None
    except (TypeError, ValueError):
        return None, None
    return minimum, maximum


def _type_matches(code: str, metadata: dict[str, dict[str, Any]], expected: set[str]) -> bool:
    """Reject contradictory types while tolerating genuinely absent metadata."""
    value_type = metadata.get(code, {}).get("type")
    if not value_type:
        return True
    return str(value_type).lower() in {item.lower() for item in expected}


def _enum_range(code: str, metadata: dict[str, dict[str, Any]]) -> list[str]:
    values = _values_for(code, metadata)
    options = values.get("range")
    if not isinstance(options, list):
        return []
    return [str(item) for item in options]


def _numeric_details(
    code: str, metadata: dict[str, dict[str, Any]]
) -> tuple[float, float, float, float] | None:
    """Return scaled min/max/step and multiplier for an Integer capability."""
    values = _values_for(code, metadata)
    try:
        minimum = float(values["min"])
        maximum = float(values["max"])
        step = float(values.get("step", 1))
        scale_digits = int(values.get("scale", 0))
    except (KeyError, TypeError, ValueError):
        return None
    multiplier = 10 ** (-scale_digits)
    return minimum * multiplier, maximum * multiplier, step * multiplier, multiplier


def _climate_mode_set(options: list[str]) -> str | None:
    """Map only Tuya enum sets already understood by LocalTuya climate."""
    values = set(options)
    candidates = (
        ({"auto", "cold", "hot", "wet", "wind"}, "Auto/Cold/Dry/Wind/Hot"),
        ({"cold", "dehumidify", "hot"}, "Cold/Dehumidify/Hot"),
        ({"manual", "auto"}, "manual/auto"),
        ({"Manual", "Auto"}, "Manual/Auto"),
        ({"MANUAL", "AUTO"}, "MANUAL/AUTO"),
        ({"Manual", "Program"}, "Manual/Program"),
        ({"m", "p"}, "m/p"),
        ({"0", "1"}, "1/0"),
    )
    for required, name in candidates:
        if required.issubset(values):
            return name
    return None


def _sensor(
    dp: int,
    name: str,
    device_class: str,
    unit: str,
    scaling: float | None = None,
    *,
    translation_key: str | None = None,
    enabled_default: bool = True,
) -> dict[str, Any]:
    entity: dict[str, Any] = {
        CONF_ID: dp,
        CONF_PLATFORM: "sensor",
        CONF_FRIENDLY_NAME: name,
        CONF_DEVICE_CLASS: device_class,
        CONF_UNIT_OF_MEASUREMENT: unit,
        CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: enabled_default,
    }
    if translation_key:
        entity[CONF_TRANSLATION_KEY] = translation_key
    if scaling is not None and scaling != 1:
        entity[CONF_SCALING] = scaling
    return entity


def analyze_auto_entities(
    spec: dict[str, Any] | None,
    available_dp_ids: set[int],
    device_name: str,
) -> AutoConfigReport:
    """Build conservative entities and a diagnostic report from Tuya capabilities."""
    report = AutoConfigReport()
    if not spec:
        return report

    code_to_dp = _dp_code_map(spec)
    metadata = _metadata_by_code(spec)
    known_codes = set(code_to_dp)
    consumed: set[str] = set()

    def dp(code: str, expected_types: set[str] | None = None) -> int | None:
        value = code_to_dp.get(code)
        if value is None:
            return None
        if value not in available_dp_ids:
            report.missing_local_dps.append(code)
            return None
        if expected_types and not _type_matches(code, metadata, expected_types):
            report.rejected_codes.append(code)
            return None
        consumed.add(code)
        return value

    entities: list[dict[str, Any]] = []

    # Light profile.
    light_power = dp("switch_led", {"Boolean"})
    if light_power is not None:
        entity: dict[str, Any] = {
            CONF_ID: light_power,
            CONF_PLATFORM: "light",
            CONF_FRIENDLY_NAME: device_name,
        }
        bright_v2 = dp("bright_value_v2", {"Integer"})
        bright_v1 = None if bright_v2 is not None else dp("bright_value", {"Integer"})
        temp_v2 = dp("temp_value_v2", {"Integer"})
        temp_v1 = None if temp_v2 is not None else dp("temp_value", {"Integer"})
        color_v2 = dp("colour_data_v2", {"Json", "String"})
        color_v1 = None if color_v2 is not None else dp("colour_data", {"Json", "String"})
        scene_v2 = dp("scene_data_v2", {"String", "Json"})
        scene_v1 = None if scene_v2 is not None else dp("scene_data", {"String", "Json"})
        optional = {
            CONF_BRIGHTNESS: bright_v2 or bright_v1,
            CONF_COLOR_TEMP: temp_v2 or temp_v1,
            CONF_COLOR_MODE: dp("work_mode", {"Enum"}),
            CONF_COLOR: color_v2 or color_v1,
            CONF_SCENE: scene_v2 or scene_v1,
        }
        entity.update({key: value for key, value in optional.items() if value is not None})

        brightness_code = "bright_value_v2" if bright_v2 is not None else "bright_value"
        lower, upper = _range_for(brightness_code, metadata)
        if lower is not None:
            entity[CONF_BRIGHTNESS_LOWER] = lower
        if upper is not None:
            entity[CONF_BRIGHTNESS_UPPER] = upper
        entities.append(entity)

    # Generic socket/relay profile.
    switch_dp = dp("switch_1", {"Boolean"})
    if switch_dp is not None:
        entities.append(
            {
                CONF_ID: switch_dp,
                CONF_PLATFORM: "switch",
                CONF_FRIENDLY_NAME: device_name,
                CONF_RESTORE_ON_RECONNECT: False,
                CONF_PASSIVE_ENTITY: False,
            }
        )

    # Electrical telemetry.
    sensor_defs = (
        ("cur_power", "Power", "power", "W", None),
        ("cur_current", "Current", "current", "mA", None),
        ("cur_voltage", "Voltage", "voltage", "V", None),
        ("add_ele", "Energy", "energy", "kWh", 0.001),
    )
    for code, suffix, device_class, unit, fallback_scale in sensor_defs:
        sensor_dp = dp(code, {"Integer"})
        if sensor_dp is None:
            continue
        scale = _scale_for(code, metadata)
        if scale is None:
            scale = fallback_scale
        entities.append(
            _sensor(
                sensor_dp,
                f"{device_name} {suffix}",
                device_class,
                unit,
                scale,
                translation_key=code,
                # add_ele is firmware-dependent on some products. Keep it
                # discoverable, but do not enable it automatically.
                enabled_default=(code != "add_ele"),
            )
        )

    # Experimental complex-family profiles. These are category-gated and
    # disabled by default. They only use Tuya standard semantic codes and
    # metadata; no brand/product/DP-number matching is performed.
    category = str(spec.get("category") or spec.get("category_code") or "").lower()
    writable_codes = _function_codes(spec)

    def candidate(code: str, expected_types: set[str], writable: bool | None = None) -> int | None:
        value = code_to_dp.get(code)
        if value is None or value not in available_dp_ids:
            return None
        if not _type_matches(code, metadata, expected_types):
            return None
        if writable is True and code not in writable_codes:
            return None
        if writable is False and code in writable_codes:
            return None
        return value

    def consume(*codes: str) -> None:
        consumed.update(code for code in codes if code and code in code_to_dp)

    # Covers / curtains (Tuya categories cl, clkg, curtain robot).  Only the
    # standard open/stop/close command set is auto-created. Percentage
    # positioning is enabled only when a 0..100 integer capability is exposed.
    if category in {"cl", "clkg", "jdcljqr"}:
        control_dp = candidate("control", {"Enum"}, writable=True)
        control_options = _enum_range("control", metadata)
        if control_dp is not None and {"open", "stop", "close"}.issubset(set(control_options)):
            cover_entity: dict[str, Any] = {
                CONF_ID: control_dp,
                CONF_PLATFORM: "cover",
                CONF_FRIENDLY_NAME: device_name,
                CONF_COMMANDS_SET: "open_close_stop",
                CONF_POSITIONING_MODE: "none",
                CONF_POSITION_INVERTED: False,
                CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
            }
            set_pos_dp = candidate("percent_control", {"Integer"}, writable=True)
            current_pos_dp = candidate("percent_state", {"Integer"})
            pos_details = _numeric_details("percent_control", metadata) if set_pos_dp is not None else None
            if set_pos_dp is not None and pos_details is not None:
                pmin, pmax, _pstep, pscale = pos_details
                if pmin == 0 and pmax == 100 and pscale == 1:
                    cover_entity[CONF_POSITIONING_MODE] = "position"
                    cover_entity[CONF_SET_POSITION_DP] = set_pos_dp
                    cover_entity[CONF_CURRENT_POSITION_DP] = current_pos_dp or set_pos_dp
                    consume("percent_control")
                    if current_pos_dp is not None:
                        consume("percent_state")
            entities.append(cover_entity)
            consume("control")

    # Fans. Standard fs uses `switch`; ceiling fan-light devices commonly use
    # `fan_switch`. Speed may be an Integer range or an Enum ordered list.
    if category in {"fs", "fsd", "kj"}:
        fan_power_code = "fan_switch" if candidate("fan_switch", {"Boolean"}, writable=True) is not None else "switch"
        fan_power_dp = candidate(fan_power_code, {"Boolean"}, writable=True)
        if fan_power_dp is not None:
            fan_entity: dict[str, Any] = {
                CONF_ID: fan_power_dp,
                CONF_PLATFORM: "fan",
                CONF_FRIENDLY_NAME: device_name,
                CONF_FAN_SPEED_MIN: 1,
                CONF_FAN_SPEED_MAX: 9,
                CONF_FAN_ORDERED_LIST: "disabled",
                CONF_FAN_DPS_TYPE: "str",
                CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
            }
            speed_code = None
            for code in ("fan_speed_percent", "fan_speed", "fan_speed_enum", "windspeed"):
                speed_dp = candidate(code, {"Integer", "Enum"}, writable=True)
                if speed_dp is None:
                    continue
                value_type = str(metadata.get(code, {}).get("type") or "").lower()
                if value_type == "integer":
                    details = _numeric_details(code, metadata)
                    if details is None:
                        continue
                    minimum, maximum, _step, multiplier = details
                    if multiplier != 1 or maximum <= minimum:
                        continue
                    fan_entity[CONF_FAN_SPEED_CONTROL] = speed_dp
                    fan_entity[CONF_FAN_SPEED_MIN] = max(1, int(minimum))
                    fan_entity[CONF_FAN_SPEED_MAX] = int(maximum)
                    fan_entity[CONF_FAN_DPS_TYPE] = "int"
                    speed_code = code
                    break
                options = _enum_range(code, metadata)
                if len(options) >= 2:
                    fan_entity[CONF_FAN_SPEED_CONTROL] = speed_dp
                    fan_entity[CONF_FAN_ORDERED_LIST] = ",".join(options)
                    fan_entity[CONF_FAN_DPS_TYPE] = "str"
                    speed_code = code
                    break
            oscillation_code = None
            for code in ("switch_horizontal", "switch_vertical"):
                osc_dp = candidate(code, {"Boolean"}, writable=True)
                if osc_dp is not None:
                    fan_entity[CONF_FAN_OSCILLATING_CONTROL] = osc_dp
                    oscillation_code = code
                    break
            direction_dp = candidate("fan_direction", {"Enum"}, writable=True)
            direction_options = set(_enum_range("fan_direction", metadata))
            if direction_dp is not None and {"forward", "reverse"}.issubset(direction_options):
                fan_entity[CONF_FAN_DIRECTION] = direction_dp
                fan_entity[CONF_FAN_DIRECTION_FWD] = "forward"
                fan_entity[CONF_FAN_DIRECTION_REV] = "reverse"
                consume("fan_direction")
            entities.append(fan_entity)
            consume(fan_power_code)
            if speed_code:
                consume(speed_code)
            if oscillation_code:
                consume(oscillation_code)

    # Thermostats / HVAC. Creation requires a writable switch, target
    # temperature, current temperature, and a mode enum that LocalTuya can map
    # without guessing. Extra unsupported Tuya modes remain available manually.
    if category in {"wk", "kt", "ktkzq", "qn"}:
        climate_power_dp = candidate("switch", {"Boolean"}, writable=True)
        target_code = "temp_set_f" if candidate("temp_set_f", {"Integer"}, writable=True) is not None else "temp_set"
        target_dp = candidate(target_code, {"Integer"}, writable=True)
        current_dp = candidate("temp_current", {"Integer"})
        mode_dp = candidate("mode", {"Enum"}, writable=True)
        mode_set = _climate_mode_set(_enum_range("mode", metadata)) if mode_dp is not None else None
        target_details = _numeric_details(target_code, metadata) if target_dp is not None else None
        current_details = _numeric_details("temp_current", metadata) if current_dp is not None else None
        if all((climate_power_dp is not None, target_dp is not None, current_dp is not None, mode_dp is not None, mode_set, target_details, current_details)):
            tmin, tmax, tstep, target_precision = target_details
            _cmin, _cmax, _cstep, current_precision = current_details
            climate_entity: dict[str, Any] = {
                CONF_ID: climate_power_dp,
                CONF_PLATFORM: "climate",
                CONF_FRIENDLY_NAME: device_name,
                CONF_TARGET_TEMPERATURE_DP: target_dp,
                CONF_CURRENT_TEMPERATURE_DP: current_dp,
                CONF_TEMPERATURE_STEP: tstep,
                CONF_TEMP_MIN: tmin,
                CONF_TEMP_MAX: tmax,
                CONF_PRECISION: current_precision,
                CONF_TARGET_PRECISION: target_precision,
                CONF_HVAC_MODE_DP: mode_dp,
                CONF_HVAC_MODE_SET: mode_set,
                CONF_HEURISTIC_ACTION: True,
                CONF_TEMPERATURE_UNIT: "fahrenheit" if target_code.endswith("_f") else "celsius",
                CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
            }
            entities.append(climate_entity)
            consume("switch", target_code, "temp_current", "mode")

    # Robot vacuums. The existing LocalTuya vacuum platform needs a status DP
    # plus a separate start/pause DP. We accept the Tuya standard `mode` as the
    # status DP, or the common `robot_state` extension when available.
    if category == "sd":
        state_code = "robot_state" if candidate("robot_state", {"Enum"}) is not None else "mode"
        state_dp = candidate(state_code, {"Enum"})
        power_go_code = "power_go" if candidate("power_go", {"Boolean"}, writable=True) is not None else "clean_switch"
        power_go_dp = candidate(power_go_code, {"Boolean"}, writable=True)
        state_options = _enum_range(state_code, metadata)
        if state_dp is not None and power_go_dp is not None and state_options:
            state_set = set(state_options)
            idle = [x for x in ("standby", "sleep", "fullcharge") if x in state_set]
            docked = [x for x in ("charging", "chargecompleted", "fullcharge") if x in state_set]
            returning = next((x for x in ("docking", "chargego") if x in state_set), "docking")
            paused = next((x for x in ("paused", "pause") if x in state_set), "paused")
            stop_status = "standby" if "standby" in state_set else (idle[0] if idle else state_options[0])
            vacuum_entity: dict[str, Any] = {
                CONF_ID: state_dp,
                CONF_PLATFORM: "vacuum",
                CONF_FRIENDLY_NAME: device_name,
                CONF_POWERGO_DP: power_go_dp,
                CONF_IDLE_STATUS_VALUE: ",".join(idle or ["standby"]),
                CONF_DOCKED_STATUS_VALUE: ",".join(docked or ["charging", "chargecompleted"]),
                CONF_RETURNING_STATUS_VALUE: returning,
                CONF_PAUSED_STATE: paused,
                CONF_STOP_STATUS: stop_status,
                CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
            }
            mode_dp = candidate("mode", {"Enum"}, writable=True)
            mode_options = _enum_range("mode", metadata)
            if mode_dp is not None and mode_options:
                vacuum_entity[CONF_MODE_DP] = mode_dp
                vacuum_entity[CONF_MODES] = ",".join(mode_options)
                if "chargego" in mode_options:
                    vacuum_entity[CONF_RETURN_MODE] = "chargego"
                consume("mode")
            for code in ("battery", "battery_percentage"):
                battery_dp = candidate(code, {"Integer"})
                if battery_dp is not None:
                    vacuum_entity[CONF_BATTERY_DP] = battery_dp
                    consume(code)
                    break
            for code in ("suction", "fan_mode"):
                fan_dp = candidate(code, {"Enum"}, writable=True)
                fan_options = _enum_range(code, metadata)
                if fan_dp is not None and fan_options:
                    vacuum_entity[CONF_FAN_SPEED_DP] = fan_dp
                    vacuum_entity[CONF_FAN_SPEEDS] = ",".join(fan_options)
                    consume(code)
                    break
            for conf_key, codes in (
                (CONF_CLEAN_TIME_DP, ("cur_clean_time", "clean_time")),
                (CONF_CLEAN_AREA_DP, ("cur_clean_area", "clean_area")),
                (CONF_CLEAN_RECORD_DP, ("clean_record",)),
                (CONF_LOCATE_DP, ("seek", "locate")),
                (CONF_FAULT_DP, ("fault",)),
            ):
                for code in codes:
                    extra_dp = code_to_dp.get(code)
                    if extra_dp is not None and extra_dp in available_dp_ids:
                        vacuum_entity[conf_key] = extra_dp
                        consume(code)
                        break
            entities.append(vacuum_entity)
            consume(state_code, power_go_code)

    # Generic capability rules. These are intentionally conservative:
    # - read-only Boolean -> binary_sensor
    # - writable Enum with declared range -> select
    # - writable Integer with min/max/step and scale 0 -> number
    # Writable booleans are deliberately left manual for now because their
    # semantics can be switch, lock, enable flag, reset action, etc.
    already_consumed = set(consumed)
    for code in sorted(known_codes - already_consumed):
        meta_type = str(metadata.get(code, {}).get("type") or "").lower()
        generic_dp = code_to_dp.get(code)
        if generic_dp is None or generic_dp not in available_dp_ids:
            continue

        values = _values_for(code, metadata)

        if meta_type == "boolean" and code not in writable_codes:
            consumed.add(code)
            entities.append(
                {
                    CONF_ID: generic_dp,
                    CONF_PLATFORM: "binary_sensor",
                    CONF_FRIENDLY_NAME: f"{device_name} {_friendly_code_name(code)}",
                    "state_on": "True",
                    "state_off": "False",
                    # Unknown read-only booleans are intentionally opt-in until
                    # their semantics have been validated on real hardware.
                    CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
                }
            )
            continue

        if meta_type == "enum" and code in writable_codes:
            options = values.get("range")
            if isinstance(options, list) and len(options) >= 2 and all(
                isinstance(item, (str, int, float)) for item in options
            ):
                consumed.add(code)
                entities.append(
                    {
                        CONF_ID: generic_dp,
                        CONF_PLATFORM: "select",
                        CONF_FRIENDLY_NAME: f"{device_name} {_friendly_code_name(code)}",
                        CONF_OPTIONS: ";".join(str(item) for item in options),
                        CONF_RESTORE_ON_RECONNECT: False,
                        CONF_PASSIVE_ENTITY: False,
                        CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
                        **({CONF_TRANSLATION_KEY: code} if code in {"relay_status", "light_mode"} else {}),
                    }
                )
            continue

        if meta_type == "integer" and code in writable_codes:
            try:
                minimum = float(values["min"])
                maximum = float(values["max"])
                step = float(values.get("step", 1))
                scale = int(values.get("scale", 0))
            except (KeyError, TypeError, ValueError):
                continue
            # LocalTuya's Number platform currently writes the displayed value
            # directly to the DP. Until scaling is added there, only scale=0 is
            # safe for automatic creation.
            if scale != 0 or maximum <= minimum or step <= 0:
                continue
            consumed.add(code)
            entities.append(
                {
                    CONF_ID: generic_dp,
                    CONF_PLATFORM: "number",
                    CONF_FRIENDLY_NAME: f"{device_name} {_friendly_code_name(code)}",
                    CONF_MIN_VALUE: minimum,
                    CONF_MAX_VALUE: maximum,
                    CONF_STEPSIZE_VALUE: step,
                    CONF_RESTORE_ON_RECONNECT: False,
                    CONF_PASSIVE_ENTITY: False,
                    CONF_ENTITY_REGISTRY_ENABLED_DEFAULT: False,
                    **({CONF_TRANSLATION_KEY: code} if code == "countdown_1" else {}),
                }
            )

    # De-duplicate by HA platform + primary DP. This is deliberately independent
    # of friendly name so re-runs cannot produce a second copy of the same entity.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for entity in entities:
        key = (str(entity[CONF_PLATFORM]), int(entity[CONF_ID]))
        if key in seen:
            continue
        seen.add(key)
        unique.append(entity)

    report.entities = unique
    report.mapped_codes = sorted(consumed)
    report.ignored_codes = sorted(known_codes - consumed - set(report.missing_local_dps) - set(report.rejected_codes))
    report.missing_local_dps = sorted(set(report.missing_local_dps))
    report.rejected_codes = sorted(set(report.rejected_codes))

    _LOGGER.debug(
        "Auto-config analysis for %s: mapped=%s ignored=%s missing_local_dp=%s rejected_type=%s entities=%s",
        device_name,
        report.mapped_codes,
        report.ignored_codes,
        report.missing_local_dps,
        report.rejected_codes,
        [(e[CONF_PLATFORM], e[CONF_ID], e[CONF_FRIENDLY_NAME]) for e in unique],
    )
    return report


def build_auto_entities(
    spec: dict[str, Any] | None,
    available_dp_ids: set[int],
    device_name: str,
) -> list[dict[str, Any]]:
    """Backward-compatible helper returning only generated entities."""
    return analyze_auto_entities(spec, available_dp_ids, device_name).entities
