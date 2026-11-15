"""A problem sensor that is on when two beers need the Cold Crashing fridge at the same time."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATED
from .manager import BrewManager
from .sensor import hub_device


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities([FridgeClashSensor(entry.runtime_data, entry.entry_id)])


class FridgeClashSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Cold crash fridge clash"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, manager: BrewManager, entry_id: str) -> None:
        self._manager = manager
        self._attr_unique_id = f"{DOMAIN}_fridge_clash"
        self._attr_device_info = hub_device(entry_id)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._manager.fridge_state()["state"] == "Clash"

    @property
    def extra_state_attributes(self) -> dict:
        return {"conflicts": self._manager.fridge_state()["attributes"]["conflicts"]}
