"""Brew Tracker for Pinter: track home brews in Pinter brewing vessels."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.typing import ConfigType

from . import logic
from .const import ACTION_PREFIX, CARD_URL, DOMAIN, EVENT_MOBILE_ACTION, SIGNAL_UPDATED, VERSION
from .manager import BrewManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type BrewConfigEntry = ConfigEntry[BrewManager]

STEP = vol.In(list(logic.STEPS))
_PINTER = {vol.Required("pinter"): cv.string}
_DAYS = {
    vol.Optional("brew_days"): vol.All(vol.Coerce(int), vol.Range(*logic.BREW_DAYS_RANGE)),
    vol.Optional("crash_days"): vol.All(vol.Coerce(int), vol.Range(*logic.CRASH_DAYS_RANGE)),
    vol.Optional("cond_days"): vol.All(vol.Coerce(int), vol.Range(*logic.CONDITION_DAYS_RANGE)),
}


def _manager(hass: HomeAssistant) -> BrewManager:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Brew Tracker is not set up.")
    return entries[0].runtime_data


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the dashboard card and load it on every page, so users add no resource by hand."""
    if getattr(hass, "http", None) is None or "frontend" not in hass.config.components:
        return                       # no web front end (for example in tests)
    from homeassistant.components.frontend import add_extra_js_url
    from homeassistant.components.http import StaticPathConfig

    path = Path(__file__).parent / "www" / "brew-tracker-card.js"
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(path), False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services and the card once; the services act on the single configured entry."""
    await _async_register_card(hass)

    async def add_pinter(call: ServiceCall) -> None:
        await _manager(hass).async_add_pinter(call.data["name"])

    async def remove_pinter(call: ServiceCall) -> None:
        await _manager(hass).async_remove_pinter(call.data["pinter"])

    async def save_beer(call: ServiceCall) -> None:
        d = call.data
        await _manager(hass).async_save_beer(logic.Beer(
            name=d["name"], abv=d.get("abv", 0.0), brew_min=d.get("brew_min", 0), brew_rec=d.get("brew_rec", 0),
            cond_min=d.get("cond_min", 0), cond_rec=d.get("cond_rec", 0), crash=d.get("crash", 3),
            hopper=d.get("hopper", False)))

    async def delete_beer(call: ServiceCall) -> None:
        await _manager(hass).async_delete_beer(call.data["name"])

    async def start_brew(call: ServiceCall) -> ServiceResponse:
        d = call.data
        return await _manager(hass).async_start_brew(
            d["pinter"], d["beer"], brew_days=d.get("brew_days"), crash_days=d.get("crash_days"),
            cond_days=d.get("cond_days"), abv=d.get("abv"), hopper=d.get("hopper"), started=d.get("started"))

    async def check_brew(call: ServiceCall) -> ServiceResponse:
        d = call.data
        manager = _manager(hass)
        beer = manager.beer(d["beer"])
        return manager.check_new_brew(
            d.get("pinter"), beer, brew_days=d.get("brew_days", beer.default_brew_days()),
            crash_days=d.get("crash_days", beer.crash if manager.fridge_capacity > 0 else 0), cond_days=d.get("cond_days", beer.default_cond_days()),
            started=d.get("started"))

    async def move_on(call: ServiceCall) -> None:
        await _manager(hass).async_move_on(call.data["pinter"], call.data.get("from_step"))

    async def go_back(call: ServiceCall) -> None:
        await _manager(hass).async_go_back(call.data["pinter"])

    async def empty(call: ServiceCall) -> None:
        await _manager(hass).async_empty(call.data["pinter"])

    async def test_notification(call: ServiceCall) -> None:
        manager = _manager(hass)
        pid = manager.pinter_id(call.data["pinter"])
        await manager.async_send(pid, test=True)

    svc = hass.services.async_register
    svc(DOMAIN, "add_pinter", add_pinter, vol.Schema({vol.Required("name"): cv.string}))
    svc(DOMAIN, "remove_pinter", remove_pinter, vol.Schema(_PINTER))
    svc(DOMAIN, "save_beer", save_beer, vol.Schema({
        vol.Required("name"): cv.string,
        vol.Optional("abv"): vol.All(vol.Coerce(float), vol.Range(0, 20)),
        vol.Optional("brew_min"): vol.All(vol.Coerce(int), vol.Range(0, 14)),
        vol.Optional("brew_rec"): vol.All(vol.Coerce(int), vol.Range(0, 14)),
        vol.Optional("cond_min"): vol.All(vol.Coerce(int), vol.Range(0, 30)),
        vol.Optional("cond_rec"): vol.All(vol.Coerce(int), vol.Range(0, 30)),
        vol.Optional("crash"): vol.All(vol.Coerce(int), vol.Range(*logic.CRASH_DAYS_RANGE)),
        vol.Optional("hopper"): cv.boolean,
    }))
    svc(DOMAIN, "delete_beer", delete_beer, vol.Schema({vol.Required("name"): cv.string}))
    svc(DOMAIN, "start_brew", start_brew, vol.Schema({
        **_PINTER, vol.Required("beer"): cv.string, **_DAYS,
        vol.Optional("abv"): vol.All(vol.Coerce(float), vol.Range(0, 20)),
        vol.Optional("hopper"): cv.boolean,
        vol.Optional("started"): cv.datetime,
    }), supports_response=SupportsResponse.OPTIONAL)
    svc(DOMAIN, "check_brew", check_brew, vol.Schema({
        vol.Optional("pinter"): cv.string, vol.Required("beer"): cv.string, **_DAYS,
        vol.Optional("started"): cv.datetime,
    }), supports_response=SupportsResponse.ONLY)
    svc(DOMAIN, "move_on", move_on, vol.Schema({**_PINTER, vol.Optional("from_step"): STEP}))
    svc(DOMAIN, "go_back", go_back, vol.Schema(_PINTER))
    svc(DOMAIN, "empty", empty, vol.Schema(_PINTER))
    svc(DOMAIN, "send_test_notification", test_notification, vol.Schema(_PINTER))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BrewConfigEntry) -> bool:
    manager = BrewManager(hass, entry)
    await manager.async_load()
    entry.runtime_data = manager

    async def _tick(_now: datetime) -> None:
        await manager.async_check_due()
        async_dispatcher_send(hass, SIGNAL_UPDATED)      # the day count and overdue flag change with time

    @callback
    def _on_action(event: Event) -> None:
        """The "Done - I moved it" button on a notification: BREW_TRACKER_NEXT|<pinter id>|<step it was on>."""
        action = str(event.data.get("action", ""))
        if not action.startswith(ACTION_PREFIX + "|"):
            return
        try:
            _prefix, pid, step = action.split("|", 2)
        except ValueError:
            return
        hass.async_create_task(manager.async_move_on(pid, step, by_id=True))

    entry.async_on_unload(async_track_time_interval(hass, _tick, timedelta(minutes=1)))
    entry.async_on_unload(hass.bus.async_listen(EVENT_MOBILE_ACTION, _on_action))
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await manager.async_check_due()
    return True


async def _async_reload(hass: HomeAssistant, entry: BrewConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BrewConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
