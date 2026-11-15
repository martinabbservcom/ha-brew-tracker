"""Sensors: one per Pinter (its step and plan), the beer inventory, and the Cold Crashing fridge."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_NEW_PINTER, SIGNAL_UPDATED
from .manager import BrewManager


def hub_device(entry_id: str) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "hub")}, name="Brew Tracker", manufacturer="Brew Tracker for Pinter (unofficial)")


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    manager: BrewManager = entry.runtime_data
    async_add_entities([BeerInventorySensor(manager, entry.entry_id), FridgeSensor(manager, entry.entry_id)]
                       + [PinterSensor(manager, pid) for pid in manager.pinters])

    @callback
    def _new_pinter(pid: str) -> None:
        async_add_entities([PinterSensor(manager, pid)])

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW_PINTER, _new_pinter))


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: BrewManager) -> None:
        self._manager = manager

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()


class PinterSensor(_Base):
    """The state is the Pinter's step (Empty, Brewing, Cold Crashing, Conditioning, Ready to drink)."""

    _attr_name = None
    _attr_icon = "mdi:beer"

    def __init__(self, manager: BrewManager, pinter_id: str) -> None:
        super().__init__(manager)
        self._pid = pinter_id
        self._attr_unique_id = f"{DOMAIN}_pinter_{pinter_id}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, pinter_id)}, name=manager.pinters[pinter_id],
                                            manufacturer="Pinter (unofficial)", via_device=(DOMAIN, "hub"))

    @callback
    def _refresh(self) -> None:
        if self._pid not in self._manager.pinters:          # the Pinter was removed
            registry = er.async_get(self.hass)
            if self.entity_id and registry.async_get(self.entity_id):
                registry.async_remove(self.entity_id)
            self.hass.async_create_task(self.async_remove(force_remove=True))
            return
        self.async_write_ha_state()

    @property
    def native_value(self) -> str:
        return self._manager.pinter_state(self._pid)["state"] if self._pid in self._manager.pinters else "Empty"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self._pid not in self._manager.pinters:
            return {}
        return self._manager.pinter_state(self._pid)["attributes"]


class BeerInventorySensor(_Base):
    _attr_name = "Beer inventory"
    _attr_icon = "mdi:glass-mug-variant"

    def __init__(self, manager: BrewManager, entry_id: str) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{DOMAIN}_beers"
        self._attr_device_info = hub_device(entry_id)

    @property
    def native_value(self) -> int:
        return len(self._manager.beers)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"beers": self._manager.beers_attribute(), "empty_pinters": self._manager.empty_pinters(),
                "pinters": sorted(self._manager.pinters.values(), key=str.casefold)}


class FridgeSensor(_Base):
    """Free, In use or Clash for the one Cold Crashing fridge."""

    _attr_name = "Cold crash fridge"
    _attr_icon = "mdi:fridge-outline"

    def __init__(self, manager: BrewManager, entry_id: str) -> None:
        super().__init__(manager)
        self._attr_unique_id = f"{DOMAIN}_fridge"
        self._attr_device_info = hub_device(entry_id)

    @property
    def native_value(self) -> str:
        return self._manager.fridge_state()["state"]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self._manager.fridge_state()["attributes"]
