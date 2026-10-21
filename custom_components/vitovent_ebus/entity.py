"""Base entity."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .controller import VitoventController


class VitoventEntity(Entity):
    """Common device and update handling."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: VitoventController, key: str, translation_key: str | None = None,
                 placeholders: dict[str, str] | None = None) -> None:
        self.controller = controller
        self._attr_unique_id = f"{controller.entry.entry_id}_{key}"
        self._attr_translation_key = translation_key or key
        if placeholders:
            self._attr_translation_placeholders = placeholders
        software = controller.value("SoftwareVersion")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller.entry.entry_id)},
            name="Vitovent 300-W",
            manufacturer="Viessmann (Brink)",
            model="Vitovent 300-W / Renovent Excellent",
            sw_version=str(software).strip() if software else None,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, self.controller.signal, self.async_write_ha_state))
