"""Binary sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VitoventConfigEntry
from .controller import VitoventController
from .entity import VitoventEntity


@dataclass(frozen=True, kw_only=True)
class VitoventBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[VitoventController], bool | None]


BINARY: tuple[VitoventBinaryDescription, ...] = (
    VitoventBinaryDescription(key="cooking", device_class=BinarySensorDeviceClass.RUNNING, icon="mdi:stove",
                              value_fn=lambda c: c.cooking),
    VitoventBinaryDescription(key="boost_active", device_class=BinarySensorDeviceClass.RUNNING, icon="mdi:fan-plus",
                              value_fn=lambda c: c.boost_active),
    VitoventBinaryDescription(key="filter_change_needed", device_class=BinarySensorDeviceClass.PROBLEM,
                              icon="mdi:air-filter", value_fn=lambda c: c.filter_change_needed),
    # unit has not followed the target stage for 10 min (or ebusd delivers nothing) – only while control is on
    VitoventBinaryDescription(key="stage_mismatch", device_class=BinarySensorDeviceClass.PROBLEM, icon="mdi:fan-alert",
                              value_fn=lambda c: c.mismatch),
)


async def async_setup_entry(hass: HomeAssistant, entry: VitoventConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(VitoventBinary(entry.runtime_data, d) for d in BINARY)


class VitoventBinary(VitoventEntity, BinarySensorEntity):
    entity_description: VitoventBinaryDescription

    def __init__(self, controller: VitoventController, description: VitoventBinaryDescription) -> None:
        super().__init__(controller, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.controller)
