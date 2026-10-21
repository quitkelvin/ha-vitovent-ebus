"""Sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VitoventConfigEntry
from .const import EBUS_TO_STAGE, REASONS, STAGES
from .controller import VitoventController
from .entity import VitoventEntity


@dataclass(frozen=True, kw_only=True)
class VitoventSensorDescription(SensorEntityDescription):
    value_fn: Callable[[VitoventController], Any]
    attrs_fn: Callable[[VitoventController], dict[str, Any]] | None = None


def _msg(name: str) -> Callable[[VitoventController], Any]:
    return lambda c: c.number(name)


def _raw(name: str) -> Callable[[VitoventController], Any]:
    return lambda c: (str(v).strip() if (v := c.value(name)) is not None else None)


def _enum(name: str, options: list[str]) -> Callable[[VitoventController], Any]:
    """ebusd text (e.g. "Closed") -> lowercase enum option, unknown texts -> None."""
    return lambda c: (v if (v := str(c.value(name) or "").strip().lower()) in options else None)


FLOW = dict(native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR, state_class=SensorStateClass.MEASUREMENT,
            device_class=SensorDeviceClass.VOLUME_FLOW_RATE)
TEMP = dict(native_unit_of_measurement=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE,
            state_class=SensorStateClass.MEASUREMENT)
PRESS = dict(native_unit_of_measurement=UnitOfPressure.PA, device_class=SensorDeviceClass.PRESSURE,
             state_class=SensorStateClass.MEASUREMENT)

SENSORS: tuple[VitoventSensorDescription, ...] = (
    VitoventSensorDescription(
        key="target_stage", device_class=SensorDeviceClass.ENUM, options=STAGES, icon="mdi:fan-auto",
        value_fn=lambda c: c.target,
        attrs_fn=lambda c: {"reason": c.reason, "inputs_unavailable": c.inputs_unavailable,
                            "control": c.control,
                            "time_program": [f"{x['days']} {x['start']:%H:%M}-{x['end']:%H:%M} {x['stage']}"
                                             for x in c.slots if x["active"]]},
    ),
    VitoventSensorDescription(
        key="reason", device_class=SensorDeviceClass.ENUM, options=REASONS, icon="mdi:help-circle-outline",
        value_fn=lambda c: c.reason,
    ),
    VitoventSensorDescription(
        key="stage", device_class=SensorDeviceClass.ENUM, options=sorted(set(EBUS_TO_STAGE.values())), icon="mdi:fan",
        value_fn=lambda c: c.stage,
    ),
    VitoventSensorDescription(key="supply_flow", value_fn=_msg("TatsaechlicheZuluftmenge"), **FLOW),
    VitoventSensorDescription(key="exhaust_flow", value_fn=_msg("TatsaechlicheAbluftmenge"), **FLOW),
    VitoventSensorDescription(key="supply_fan_speed", native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
                              state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC,
                              icon="mdi:fan", value_fn=_msg("TatsaechlicheDrehzahlZuluft")),
    VitoventSensorDescription(key="exhaust_fan_speed", native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
                              state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC,
                              icon="mdi:fan", value_fn=_msg("TatsaechlicheDrehzahlAbluft")),
    VitoventSensorDescription(key="extract_temperature", value_fn=_msg("Ablufttemperatur"), **TEMP),
    VitoventSensorDescription(key="outdoor_temperature", value_fn=_msg("Aussenlufttemperatur"), **TEMP),
    VitoventSensorDescription(key="bypass", icon="mdi:valve", device_class=SensorDeviceClass.ENUM,
                              options=["initializing", "opening", "closing", "open", "closed", "error", "calibrating"],
                              value_fn=_enum("StatusBypass", ["initializing", "opening", "closing", "open", "closed", "error", "calibrating"])),
    VitoventSensorDescription(key="frost_protection", icon="mdi:snowflake-alert", entity_category=EntityCategory.DIAGNOSTIC,
                              value_fn=_raw("StatusFrostschutz")),
    VitoventSensorDescription(key="fan_status", icon="mdi:fan-alert", entity_category=EntityCategory.DIAGNOSTIC,
                              value_fn=_raw("StatusVentilator")),
    VitoventSensorDescription(key="supply_pressure", value_fn=_msg("IstwertZuluftdruck"), **PRESS),
    VitoventSensorDescription(key="exhaust_pressure", value_fn=_msg("IstwertAbluftdruck"), **PRESS),
    VitoventSensorDescription(key="filter_status", icon="mdi:air-filter", device_class=SensorDeviceClass.ENUM,
                              options=["clean", "dirty"], value_fn=_enum("Filtermeldung", ["clean", "dirty"])),
    VitoventSensorDescription(key="filter_days", native_unit_of_measurement=UnitOfTime.DAYS, icon="mdi:calendar-clock",
                              state_class=SensorStateClass.MEASUREMENT, value_fn=_msg("FilterverwendungTage")),
    VitoventSensorDescription(key="filter_flow", native_unit_of_measurement=UnitOfVolume.CUBIC_METERS, icon="mdi:air-filter",
                              state_class=SensorStateClass.MEASUREMENT, value_fn=_msg("Filterverwendung")),
    VitoventSensorDescription(key="filter_flow_limit", native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
                              icon="mdi:air-filter", entity_category=EntityCategory.DIAGNOSTIC,
                              value_fn=_msg("MaximalerDurchsatzFilter")),
    VitoventSensorDescription(key="filter_remaining", native_unit_of_measurement=PERCENTAGE, icon="mdi:air-filter",
                              state_class=SensorStateClass.MEASUREMENT, value_fn=lambda c: c.filter_remaining),
    VitoventSensorDescription(key="filter_change_in", native_unit_of_measurement=UnitOfTime.DAYS,
                              icon="mdi:calendar-arrow-right", value_fn=lambda c: c.filter_change_in),
    VitoventSensorDescription(key="operating_hours", native_unit_of_measurement=UnitOfTime.HOURS,
                              device_class=SensorDeviceClass.DURATION, state_class=SensorStateClass.TOTAL_INCREASING,
                              value_fn=_msg("Betriebsdauer")),
    VitoventSensorDescription(key="total_flow", native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
                              state_class=SensorStateClass.TOTAL_INCREASING, icon="mdi:weather-windy",
                              value_fn=_msg("Gesamtdurchsatz")),
    VitoventSensorDescription(key="error_memory", icon="mdi:alert-circle-outline", entity_category=EntityCategory.DIAGNOSTIC,
                              value_fn=_raw("GespeicherteFehler")),
    VitoventSensorDescription(key="software", icon="mdi:chip", entity_category=EntityCategory.DIAGNOSTIC,
                              value_fn=_raw("SoftwareVersion")),
    VitoventSensorDescription(key="kitchen_power_mean", native_unit_of_measurement="W", device_class=SensorDeviceClass.POWER,
                              state_class=SensorStateClass.MEASUREMENT, entity_category=EntityCategory.DIAGNOSTIC,
                              suggested_display_precision=0, value_fn=lambda c: c.kitchen_mean),
)


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(VitoventSensor(entry.runtime_data, d) for d in SENSORS)


class VitoventSensor(VitoventEntity, SensorEntity):
    entity_description: VitoventSensorDescription

    def __init__(self, controller: VitoventController, description: VitoventSensorDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.controller)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.controller) if fn else None
