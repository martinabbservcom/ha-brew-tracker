"""The brewing rules: steps, dates, undo, the Cold Crashing fridge and the notification wording.

Pure Python with no Home Assistant imports, so it can be tested on its own. All datetimes are timezone aware and in the
user's local time zone; dates are taken in that zone.

Steps: Brewing, then Cold Crashing (optional, skipped when its days are 0; dock attached, in the fridge), then
Conditioning (dock off, the hopper goes in if the beer has one, back in the fridge in its tapping position), then Ready
to drink. A step's days count from when it started. Moving a step late pushes the later dates back.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta

BREWING = "Brewing"
COLD_CRASHING = "Cold Crashing"
CONDITIONING = "Conditioning"
READY = "Ready to drink"

STEPS = (BREWING, COLD_CRASHING, CONDITIONING, READY)
TIMED_STEPS = (BREWING, COLD_CRASHING, CONDITIONING)

BREW_DAYS_RANGE = (1, 14)
CRASH_DAYS_RANGE = (0, 14)
CONDITION_DAYS_RANGE = (1, 30)

HOW = {
    COLD_CRASHING: "Put it in the fridge with its dock attached.",
    READY: "It stays in the fridge. It is ready to drink.",
}


@dataclass(frozen=True)
class Beer:
    """A beer in the inventory. min = the beer's minimum days (0 = not set), rec = the recommended days."""

    name: str
    abv: float = 0.0
    brew_min: int = 0
    brew_rec: int = 0
    cond_min: int = 0
    cond_rec: int = 0
    crash: int = 3
    hopper: bool = False

    def default_brew_days(self) -> int:
        return self.brew_rec or self.brew_min or 10

    def default_cond_days(self) -> int:
        return self.cond_rec or self.cond_min or 5


@dataclass(frozen=True)
class Brew:
    """What is in a Pinter, and where it is up to."""

    beer: str
    abv: float
    hopper: bool
    brew_days: int
    crash_days: int
    cond_days: int
    step: str
    step_start: datetime
    prev_step: str | None = None
    prev_start: datetime | None = None
    notified: bool = False


@dataclass(frozen=True)
class FridgeWindow:
    pinter: str
    beer: str
    start: date
    end: date
    in_fridge: bool


def clamp(value: int, bounds: tuple[int, int]) -> int:
    return max(bounds[0], min(bounds[1], int(value)))


def days_for(brew: Brew, step: str) -> int:
    return {BREWING: brew.brew_days, COLD_CRASHING: brew.crash_days, CONDITIONING: brew.cond_days}.get(step, 0)


def sequence(brew: Brew) -> list[str]:
    """The timed steps this brew goes through (Cold Crashing is left out when it is 0 days)."""
    return [BREWING] + ([COLD_CRASHING] if brew.crash_days > 0 else []) + [CONDITIONING]


def next_step(brew: Brew) -> str | None:
    if brew.step == BREWING:
        return COLD_CRASHING if brew.crash_days > 0 else CONDITIONING
    return {COLD_CRASHING: CONDITIONING, CONDITIONING: READY}.get(brew.step)


def previous_in_sequence(brew: Brew) -> str | None:
    if brew.step == READY:
        return CONDITIONING
    seq = sequence(brew)
    if brew.step in seq and seq.index(brew.step) > 0:
        return seq[seq.index(brew.step) - 1]
    return None


def start_brew(beer: Beer, now: datetime, *, brew_days: int, crash_days: int, cond_days: int,
               abv: float | None = None, hopper: bool | None = None, started: datetime | None = None) -> Brew:
    """A new brew of a beer from the inventory. Days and the hopper default from the beer and can be adjusted."""
    return Brew(
        beer=beer.name,
        abv=beer.abv if abv is None else abv,
        hopper=beer.hopper if hopper is None else hopper,
        brew_days=clamp(brew_days, BREW_DAYS_RANGE),
        crash_days=clamp(crash_days, CRASH_DAYS_RANGE),
        cond_days=clamp(cond_days, CONDITION_DAYS_RANGE),
        step=BREWING,
        step_start=started or now,
    )


def due_date(brew: Brew) -> date | None:
    """The day the current step ends (the day to move it on), or None when no move is due."""
    if brew.step not in TIMED_STEPS:
        return None
    return brew.step_start.date() + timedelta(days=days_for(brew, brew.step))


def notify_at(brew: Brew, notify_time: time) -> datetime | None:
    """When the move-on notification is due: the due day at the chosen time of day."""
    due = due_date(brew)
    if due is None:
        return None
    return datetime.combine(due, notify_time, tzinfo=brew.step_start.tzinfo)


def days_left(brew: Brew, today: date) -> int | None:
    due = due_date(brew)
    return None if due is None else (due - today).days


def is_overdue(brew: Brew, now: datetime, notify_time: time) -> bool:
    left = days_left(brew, now.date())
    if left is None:
        return False
    return left < 0 or (left == 0 and now.timetz().replace(tzinfo=None) >= notify_time)


def advance(brew: Brew, now: datetime) -> Brew | None:
    """Move on to the next step. Remembers the step it left so go_back can undo this. None when there is no next step."""
    target = next_step(brew)
    if target is None:
        return None
    return replace(brew, step=target, step_start=now, prev_step=brew.step, prev_start=brew.step_start, notified=False)


def go_back(brew: Brew, now: datetime) -> Brew | None:
    """Undo the last move: back to the step it was moved from, with that step's original start time.

    Without a remembered step it goes to the one before in the sequence, starting now. A step that is already past due
    comes back marked as notified, so it does not send its notification again. None on the first step.
    """
    target = brew.prev_step if brew.prev_step and brew.prev_step != brew.step else previous_in_sequence(brew)
    if target is None:
        return None
    start = brew.prev_start or now
    restored = replace(brew, step=target, step_start=start, prev_step=None, prev_start=None, notified=False)
    due = due_date(restored)
    return replace(restored, notified=due is not None and due <= now.date())


def plan(brew: Brew) -> dict:
    """The plan as rows (step, days, from, to, status, note) and the ready-to-drink date, assuming each move is on time."""
    seq = sequence(brew)
    rows = []
    ready_on = None
    if brew.step in seq:
        idx = seq.index(brew.step)
        cursor = brew.step_start.date()
        notes = {
            BREWING: "",
            COLD_CRASHING: "Fridge, dock attached",
            CONDITIONING: "Dock off, hopper in, fridge, tapping position" if brew.hopper else "Dock off, fridge, tapping position",
        }
        for i, step in enumerate(seq):
            if i < idx:
                rows.append({"step": step, "days": days_for(brew, step), "from": None, "to": None, "status": "done", "note": notes[step]})
                continue
            end = cursor + timedelta(days=days_for(brew, step))
            rows.append({"step": step, "days": days_for(brew, step), "from": cursor, "to": end,
                         "status": "now" if i == idx else "next", "note": notes[step]})
            cursor = end
        ready_on = cursor
    return {"rows": rows, "ready_on": ready_on}


def how_to_move(brew: Brew, target: str | None) -> str:
    if target == CONDITIONING:
        if brew.hopper:
            return "Take the dock off, put the hopper in, and put it back in the fridge in its tapping position."
        return "Take the dock off and put it back in the fridge in its tapping position."
    return HOW.get(target or "", "")


def hopper_note(brew: Brew) -> str:
    if brew.hopper and brew.step in (BREWING, COLD_CRASHING):
        return "The hopper goes in when the dock comes off."
    return ""


# ----------------------------------------------------------------------------- the one Cold Crashing fridge

def fridge_windows(brews: dict[str, tuple[str, Brew]]) -> list[FridgeWindow]:
    """Cold Crash windows of brews that still need the fridge. brews maps a Pinter id to (Pinter name, brew)."""
    out = []
    for pinter, (name, brew) in brews.items():
        if brew.step not in (BREWING, COLD_CRASHING) or brew.crash_days <= 0:
            continue
        start = brew.step_start.date()
        if brew.step == BREWING:
            start += timedelta(days=brew.brew_days)
        out.append(FridgeWindow(name, brew.beer, start, start + timedelta(days=brew.crash_days), brew.step == COLD_CRASHING))
    return out


def fridge_check(windows: list[FridgeWindow]) -> dict:
    """Overlaps are clashes; one coming out and another going in on the same day is fine (a handover)."""
    conflicts, handovers = [], []
    for i, a in enumerate(windows):
        for b in windows[i + 1:]:
            if a.start < b.end and b.start < a.end:
                lo, hi = max(a.start, b.start), min(a.end, b.end)
                conflicts.append({
                    "pinters": [a.pinter, b.pinter],
                    "text": f"{a.pinter} ({a.beer}) and {b.pinter} ({b.beer}) both need the fridge for Cold Crashing "
                            f"between {fmt_short(lo)} and {fmt_short(hi)}.",
                })
            elif a.end == b.start:
                handovers.append(f"{a.pinter} comes out of the fridge and {b.pinter} goes in on {fmt_short(a.end)} (same day, so no clash).")
            elif b.end == a.start:
                handovers.append(f"{b.pinter} comes out of the fridge and {a.pinter} goes in on {fmt_short(b.end)} (same day, so no clash).")
    occupant = next((w for w in windows if w.in_fridge), None)
    state = "Clash" if conflicts else ("In use" if occupant else "Free")
    return {"state": state, "conflicts": conflicts, "handovers": handovers, "occupant": occupant}


def check_new_brew(windows: list[FridgeWindow], started: date, brew_days: int, crash_days: int,
                   exclude_pinter: str | None = None) -> tuple[str, str]:
    """Would a brew starting on `started` clash with the fridge? Returns (state, text) for the Start a brew form."""
    if crash_days <= 0:
        return "No Cold Crashing", "No Cold Crashing, so this beer will not need the fridge."
    start = started + timedelta(days=brew_days)
    end = start + timedelta(days=crash_days)
    mine = f"{fmt_short(start)} to {fmt_short(end)}"
    for w in windows:
        if w.pinter != exclude_pinter and start < w.end and w.start < end:
            return "Clash", (f"FRIDGE CLASH: this beer would be Cold Crashing {mine}, but {w.pinter} ({w.beer}) has the "
                             f"fridge {fmt_short(w.start)} to {fmt_short(w.end)}. Change the days or start it later.")
    return "Free", f"The fridge is free for this beer's Cold Crash ({mine})."


def minimum_warnings(beer: Beer, brew_days: int, cond_days: int) -> list[str]:
    out = []
    if beer.brew_min > 0 and brew_days < beer.brew_min:
        out.append(f"Brewing for {brew_days} days is below the minimum of {beer.brew_min} days for {beer.name}.")
    if beer.cond_min > 0 and cond_days < beer.cond_min:
        out.append(f"Conditioning for {cond_days} days is below the minimum of {beer.cond_min} days for {beer.name}.")
    return out


# ----------------------------------------------------------------------------- notification wording

_VERB = {BREWING: "brewing", COLD_CRASHING: "cold crashing", CONDITIONING: "conditioning"}


def move_on_message(pinter_name: str, brew: Brew, fridge_occupant: FridgeWindow | None = None) -> tuple[str, str]:
    """(title, message) for a Pinter whose current step is due. Conditioning ending says the beer is ready to drink."""
    if brew.step == CONDITIONING:
        abv = f" ({brew.abv:g}%)" if brew.abv > 0 else ""
        return f"{pinter_name} is ready", f"{pinter_name}: {brew.beer}{abv} has finished conditioning. It is ready to drink!"
    target = next_step(brew)
    message = f"{pinter_name}: {_VERB.get(brew.step, '')} {brew.beer}. Move it on to {target}. {how_to_move(brew, target)}"
    if target == COLD_CRASHING and fridge_occupant is not None and fridge_occupant.pinter != pinter_name:
        message += (f" Heads up: the cold crash fridge is in use by {fridge_occupant.pinter} ({fridge_occupant.beer}) "
                    f"until {fmt_short(fridge_occupant.end)}.")
    return f"{pinter_name}: time to move on", message


def fmt_short(d: date) -> str:
    """Wed 25 Nov"""
    return f"{d.strftime('%a')} {d.day:02d} {d.strftime('%b')}"


def fmt_long(d: date) -> str:
    """Wednesday 25 November"""
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B')}"
