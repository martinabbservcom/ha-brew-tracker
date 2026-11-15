"""Keeps the Pinters, the beer inventory and the brews, applies the rules in logic.py, and sends the notifications."""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, replace
from datetime import date, datetime, time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import logic
from .const import (ACTION_PREFIX, CONF_CONDITIONING_IN_FRIDGE, CONF_FRIDGE_CAPACITY, CONF_NOTIFY, CONF_NOTIFY_TIME,
                    DEFAULT_FRIDGE_CAPACITY, DEFAULT_NOTIFY_TIME, DOMAIN, EMPTY, SIGNAL_NEW_PINTER, SIGNAL_UPDATED,
                    STORAGE_VERSION)

_LOGGER = logging.getLogger(__name__)


def _dt_out(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dt_in(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


def brew_to_dict(brew: logic.Brew) -> dict[str, Any]:
    data = asdict(brew)
    data["step_start"] = _dt_out(brew.step_start)
    data["prev_start"] = _dt_out(brew.prev_start)
    return data


def brew_from_dict(data: dict[str, Any]) -> logic.Brew:
    data = dict(data)
    data["step_start"] = _dt_in(data["step_start"])
    data["prev_start"] = _dt_in(data.get("prev_start"))
    return logic.Brew(**data)


class BrewManager:
    """All the data and the actions on it. Entities and services use this; nothing else touches the store."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.data")
        self.pinters: dict[str, str] = {}          # id -> name
        self.beers: dict[str, logic.Beer] = {}      # name -> beer
        self.brews: dict[str, logic.Brew] = {}      # pinter id -> brew (a Pinter with no brew is empty)

    # ------------------------------------------------------------------------------------------ storage
    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.pinters = dict(data.get("pinters", {}))
        self.beers = {name: logic.Beer(**b) for name, b in data.get("beers", {}).items()}
        self.brews = {pid: brew_from_dict(b) for pid, b in data.get("brews", {}).items() if pid in self.pinters}

    async def _async_changed(self) -> None:
        await self._store.async_save({
            "pinters": self.pinters,
            "beers": {name: asdict(b) for name, b in self.beers.items()},
            "brews": {pid: brew_to_dict(b) for pid, b in self.brews.items()},
        })
        async_dispatcher_send(self.hass, SIGNAL_UPDATED)

    # ------------------------------------------------------------------------------------------ settings
    @property
    def notify_services(self) -> list[str]:
        return list(self.entry.options.get(CONF_NOTIFY, self.entry.data.get(CONF_NOTIFY, [])))

    @property
    def notify_time(self) -> time:
        text = self.entry.options.get(CONF_NOTIFY_TIME, self.entry.data.get(CONF_NOTIFY_TIME, DEFAULT_NOTIFY_TIME))
        return time.fromisoformat(text)

    def _setting(self, key: str, default):
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def fridge_capacity(self) -> int:
        """How many Pinters can be Cold Crashed at the same time. 0 means no fridge: Cold Crashing is skipped."""
        return int(self._setting(CONF_FRIDGE_CAPACITY, DEFAULT_FRIDGE_CAPACITY))

    @property
    def conditioning_in_fridge(self) -> bool:
        return bool(self._setting(CONF_CONDITIONING_IN_FRIDGE, False))

    # ------------------------------------------------------------------------------------------ lookups
    def pinter_id(self, name: str) -> str:
        wanted = (name or "").strip().casefold()
        for pid, pname in self.pinters.items():
            if pname.casefold() == wanted:
                return pid
        raise ServiceValidationError(f"There is no Pinter called {name!r}.")

    def name_of(self, pid: str) -> str:
        return self.pinters[pid]

    def empty_pinters(self) -> list[str]:
        return sorted((n for p, n in self.pinters.items() if p not in self.brews), key=str.casefold)

    def beer(self, name: str) -> logic.Beer:
        for beer_name, beer in self.beers.items():
            if beer_name.casefold() == (name or "").strip().casefold():
                return beer
        raise ServiceValidationError(f"{name!r} is not in the beer inventory. Add it first, then start the brew.")

    # ------------------------------------------------------------------------------------------ Pinters
    async def async_add_pinter(self, name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ServiceValidationError("Give the Pinter a name.")
        if name.casefold() in (n.casefold() for n in self.pinters.values()):
            raise ServiceValidationError(f"{name} is already in the inventory.")
        pid = uuid.uuid4().hex[:8]
        self.pinters[pid] = name
        await self._async_changed()
        async_dispatcher_send(self.hass, SIGNAL_NEW_PINTER, pid)
        return pid

    async def async_remove_pinter(self, name: str) -> None:
        pid = self.pinter_id(name)
        if pid in self.brews:
            raise ServiceValidationError(f"{self.pinters[pid]} has a brew in it. Empty it first.")
        del self.pinters[pid]
        await self._async_changed()

    # ------------------------------------------------------------------------------------------ beers
    async def async_save_beer(self, beer: logic.Beer) -> None:
        if not beer.name.strip():
            raise ServiceValidationError("Give the beer a name.")
        if not (beer.brew_rec or beer.brew_min):
            raise ServiceValidationError("Set a brewing time (recommended or minimum).")
        if not (beer.cond_rec or beer.cond_min):
            raise ServiceValidationError("Set a conditioning time (recommended or minimum).")
        # a beer with the same name (any capitalisation) is replaced, so this is also how a beer is edited
        for existing in [n for n in self.beers if n.casefold() == beer.name.strip().casefold()]:
            del self.beers[existing]
        self.beers[beer.name.strip()] = replace(beer, name=beer.name.strip())
        await self._async_changed()

    async def async_delete_beer(self, name: str) -> None:
        beer = self.beer(name)
        del self.beers[beer.name]
        await self._async_changed()

    # ------------------------------------------------------------------------------------------ brews
    def check_new_brew(self, pinter: str | None, beer: logic.Beer, *, brew_days: int, crash_days: int, cond_days: int,
                       started: datetime | None = None) -> dict[str, Any]:
        """What the Start a brew form shows: fridge clash, and days below the beer's minimum."""
        when = (started or dt_util.now()).date()
        if self.fridge_capacity <= 0:
            crash_days = 0
        state, text = logic.check_new_brew(self._fridge_windows(), when, brew_days, crash_days, exclude_pinter=pinter,
                                           capacity=self.fridge_capacity, cond_days=cond_days,
                                           conditioning_in_fridge=self.conditioning_in_fridge)
        warnings = logic.minimum_warnings(beer, brew_days, cond_days)
        if warnings and state != "Clash":
            state = "Below minimum"
        return {"state": state, "text": " ".join([text] + warnings), "warnings": warnings}

    async def async_start_brew(self, pinter: str, beer_name: str, *, brew_days: int | None = None,
                               crash_days: int | None = None, cond_days: int | None = None,
                               abv: float | None = None, hopper: bool | None = None,
                               started: datetime | None = None) -> dict[str, Any]:
        pid = self.pinter_id(pinter)
        if pid in self.brews:
            raise ServiceValidationError(f"{self.pinters[pid]} is not empty.")
        beer = self.beer(beer_name)
        brew_days = beer.default_brew_days() if brew_days is None else brew_days
        crash_days = beer.crash if crash_days is None else crash_days
        if self.fridge_capacity <= 0:
            crash_days = 0                     # no fridge to Cold Crash in
        cond_days = beer.default_cond_days() if cond_days is None else cond_days
        check = self.check_new_brew(self.pinters[pid], beer, brew_days=brew_days, crash_days=crash_days,
                                    cond_days=cond_days, started=started)
        self.brews[pid] = logic.start_brew(beer, dt_util.now(), brew_days=brew_days, crash_days=crash_days,
                                           cond_days=cond_days, abv=abv, hopper=hopper, started=started)
        await self._async_changed()
        return check

    def _brew(self, name: str) -> tuple[str, logic.Brew]:
        pid = self.pinter_id(name)
        if pid not in self.brews:
            raise ServiceValidationError(f"{self.pinters[pid]} is empty.")
        return pid, self.brews[pid]

    async def async_move_on(self, pinter: str, from_step: str | None = None, *, by_id: bool = False) -> bool:
        """Move a Pinter on. With from_step it only moves if it is still on that step (a stale notification does nothing)."""
        pid, brew = (pinter, self.brews[pinter]) if by_id and pinter in self.brews else (self._brew(pinter) if not by_id else (None, None))
        if brew is None:
            return False
        if from_step and brew.step != from_step:
            return False
        moved = logic.advance(brew, dt_util.now())
        if moved is None:
            return False
        self.brews[pid] = moved
        await self._async_changed()
        return True

    async def async_go_back(self, pinter: str) -> bool:
        pid, brew = self._brew(pinter)
        back = logic.go_back(brew, dt_util.now())
        if back is None:
            raise ServiceValidationError(f"{self.pinters[pid]} is on {brew.step}, which has no earlier step.")
        self.brews[pid] = back
        await self._async_changed()
        return True

    async def async_empty(self, pinter: str) -> None:
        pid = self.pinter_id(pinter)
        self.brews.pop(pid, None)
        await self._async_changed()

    # ------------------------------------------------------------------------------------------ the fridge
    def _fridge_windows(self) -> list[logic.FridgeWindow]:
        return logic.fridge_windows({pid: (self.pinters[pid], brew) for pid, brew in self.brews.items()},
                                    self.conditioning_in_fridge)

    def fridge(self) -> dict[str, Any]:
        return logic.fridge_check(self._fridge_windows(), self.fridge_capacity)

    # ------------------------------------------------------------------------------------------ notifications
    async def async_send(self, pid: str, *, test: bool = False) -> None:
        """Send the move-on (or ready) notification for a Pinter to the chosen notify services."""
        brew = self.brews.get(pid)
        if brew is None:
            return
        name = self.pinters[pid]
        check = self.fridge()
        # only worth a heads-up when the fridge is full, so the Pinter being moved in has nowhere to go
        full = self.fridge_capacity > 0 and len(check["occupants"]) >= self.fridge_capacity
        occupant = check["occupants"][0] if full else None
        title, message = logic.move_on_message(name, brew, occupant)
        if test:
            title = "TEST - " + title
        data: dict[str, Any] = {"tag": f"{DOMAIN}_{pid}"}
        if brew.step != logic.CONDITIONING:
            data["actions"] = [{"action": f"{ACTION_PREFIX}|{pid}|{brew.step}", "title": "Done - I moved it"}]
        for service in self.notify_services:
            try:
                await self.hass.services.async_call("notify", service, {"title": title, "message": message, "data": data}, blocking=True)
            except Exception:  # noqa: BLE001 - one phone failing must not stop the others
                _LOGGER.exception("Could not send the %s notification through notify.%s", name, service)

    async def async_check_due(self, now: datetime | None = None) -> None:
        """Send each Pinter's move-on notification once when its day and time arrive. A finished Conditioning becomes Ready to drink."""
        now = now or dt_util.now()
        notify_time = self.notify_time
        for pid, brew in list(self.brews.items()):
            if brew.notified or brew.step not in logic.TIMED_STEPS:
                continue
            when = logic.notify_at(brew, notify_time)
            if when is None or now < when:
                continue
            await self.async_send(pid)
            brew = replace(self.brews[pid], notified=True)
            self.brews[pid] = brew
            if brew.step == logic.CONDITIONING:
                moved = logic.advance(brew, now)
                if moved:
                    self.brews[pid] = moved
            await self._async_changed()

    # ------------------------------------------------------------------------------------------ for entities
    def pinter_state(self, pid: str) -> dict[str, Any]:
        """The state and attributes of a Pinter's sensor."""
        brew = self.brews.get(pid)
        if brew is None:
            return {"state": EMPTY, "attributes": {"pinter": self.pinters[pid], "pinter_id": pid}}
        now = dt_util.now()
        plan = logic.plan(brew)
        due = logic.due_date(brew)
        target = logic.next_step(brew)
        attrs = {
            "pinter": self.pinters[pid], "pinter_id": pid,
            "beer": brew.beer, "abv": brew.abv, "hopper": brew.hopper, "hopper_note": logic.hopper_note(brew),
            "step_days": logic.days_for(brew, brew.step), "day": (now.date() - brew.step_start.date()).days + 1,
            "started": brew.step_start.isoformat(), "due": due.isoformat() if due else None,
            "due_text": logic.fmt_long(due) if due else None, "days_left": logic.days_left(brew, now.date()),
            "overdue": logic.is_overdue(brew, now, self.notify_time), "next_step": target,
            "how": logic.how_to_move(brew, target) if brew.step != logic.CONDITIONING else logic.HOW[logic.READY],
            "ready_on": plan["ready_on"].isoformat() if plan["ready_on"] else None,
            "can_go_back": logic.go_back(brew, now) is not None,
            "plan": [{"step": r["step"], "days": r["days"], "from": r["from"].isoformat() if r["from"] else None,
                      "to": r["to"].isoformat() if r["to"] else None, "status": r["status"], "note": r["note"]}
                     for r in plan["rows"]],
            "notified": brew.notified,
        }
        return {"state": brew.step, "attributes": attrs}

    def fridge_state(self) -> dict[str, Any]:
        check = self.fridge()
        occupant = check["occupant"]
        return {"state": check["state"], "attributes": {
            "capacity": self.fridge_capacity, "conditioning_in_fridge": self.conditioning_in_fridge,
            "conflicts": [c["text"] for c in check["conflicts"]],
            "handovers": check["handovers"],
            "occupant": None if occupant is None else {"pinter": occupant.pinter, "beer": occupant.beer, "until": occupant.end.isoformat()},
        }}

    def beers_attribute(self) -> list[dict[str, Any]]:
        return [asdict(b) for b in sorted(self.beers.values(), key=lambda b: b.name.casefold())]
