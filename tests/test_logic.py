"""Tests for the brewing rules, using the real examples this was built from (Bluey and The Black One, Nov 2026)."""
from datetime import date, datetime, time, timezone

import pytest

from custom_components.brew_tracker import logic as L

UTC = timezone.utc
NINE = time(9, 0)


def dt(day, hour=15, minute=3, month=11):
    return datetime(2026, month, day, hour, minute, 37, tzinfo=UTC)


LONDON_PRIDE = L.Beer("London Pride", abv=4.7, brew_min=5, brew_rec=7, cond_min=3, cond_rec=5, crash=3)
ELVIS = L.Beer("Elvis Juice", abv=6.5, brew_min=7, brew_rec=9, cond_min=3, cond_rec=5, crash=3, hopper=True)


@pytest.fixture
def bluey():
    # started Sun 15 Nov, brew 10, crash 3, condition 5
    return L.start_brew(LONDON_PRIDE, dt(15), brew_days=10, crash_days=3, cond_days=5)


@pytest.fixture
def black_one():
    return L.start_brew(ELVIS, dt(15, 15, 37), brew_days=13, crash_days=3, cond_days=5)


def test_defaults_come_from_the_beer():
    assert ELVIS.default_brew_days() == 9 and ELVIS.default_cond_days() == 5
    assert L.Beer("Plain", brew_min=6).default_brew_days() == 6
    assert L.Beer("Nothing").default_brew_days() == 10 and L.Beer("Nothing").default_cond_days() == 5


def test_days_are_kept_within_range():
    b = L.start_brew(LONDON_PRIDE, dt(15), brew_days=99, crash_days=-4, cond_days=0)
    assert (b.brew_days, b.crash_days, b.cond_days) == (14, 0, 1)


def test_bluey_plan(bluey):
    p = L.plan(bluey)
    assert [(r["step"], r["from"], r["to"], r["status"]) for r in p["rows"]] == [
        ("Brewing", date(2026, 11, 15), date(2026, 11, 25), "now"),
        ("Cold Crashing", date(2026, 11, 25), date(2026, 11, 28), "next"),
        ("Conditioning", date(2026, 11, 28), date(2026, 12, 3), "next"),
    ]
    assert p["ready_on"] == date(2026, 12, 3)
    assert L.fmt_long(L.due_date(bluey)) == "Wednesday 25 November"
    assert L.fmt_short(date(2026, 12, 3)) == "Thu 03 Dec"


def test_black_one_plan_and_hopper(black_one):
    p = L.plan(black_one)
    assert p["ready_on"] == date(2026, 12, 6)
    assert [r["to"] for r in p["rows"]] == [date(2026, 11, 28), date(2026, 12, 1), date(2026, 12, 6)]
    assert p["rows"][2]["note"] == "Dock off, hopper in, fridge, tapping position"
    assert L.hopper_note(black_one) == "The hopper goes in when the dock comes off."


def test_skipping_cold_crash(bluey):
    b = L.start_brew(LONDON_PRIDE, dt(15), brew_days=10, crash_days=0, cond_days=5)
    assert [r["step"] for r in L.plan(b)["rows"]] == ["Brewing", "Conditioning"]
    assert L.next_step(b) == "Conditioning"


def test_notify_time_and_overdue(bluey):
    assert L.notify_at(bluey, NINE) == datetime(2026, 11, 25, 9, 0, tzinfo=UTC)
    assert L.days_left(bluey, date(2026, 11, 15)) == 10
    assert not L.is_overdue(bluey, datetime(2026, 11, 25, 8, 59, tzinfo=UTC), NINE)
    assert L.is_overdue(bluey, datetime(2026, 11, 25, 9, 0, tzinfo=UTC), NINE)
    assert L.is_overdue(bluey, datetime(2026, 11, 26, 7, 0, tzinfo=UTC), NINE)


def test_advance_walks_through_the_steps_and_remembers_where_it_came_from(bluey):
    now = dt(25, 9, 0)
    crash = L.advance(bluey, now)
    assert (crash.step, crash.step_start, crash.prev_step, crash.prev_start) == ("Cold Crashing", now, "Brewing", bluey.step_start)
    assert L.due_date(crash) == date(2026, 11, 28)
    cond = L.advance(crash, dt(28, 9, 0))
    ready = L.advance(cond, dt(12, 9, 0, month=12))
    assert (cond.step, ready.step) == ("Conditioning", "Ready to drink")
    assert L.advance(ready, dt(12, 9, 0, month=12)) is None and L.due_date(ready) is None


def test_go_back_restores_the_step_and_its_start_time(bluey):
    crash = L.advance(bluey, dt(25, 9, 0))
    back = L.go_back(crash, dt(25, 9, 5))
    assert back.step == "Brewing" and back.step_start == bluey.step_start and back.prev_step is None
    # a second undo has nothing left to undo on the first step
    assert L.go_back(back, dt(25, 9, 6)) is None


def test_go_back_to_an_overdue_step_does_not_notify_again(bluey):
    crash = L.advance(bluey, dt(27, 12, 0))          # moved on late, on 27 Nov
    back = L.go_back(crash, dt(27, 12, 1))
    assert back.step == "Brewing" and back.notified is True      # Brewing was due 25 Nov, long past
    fresh = L.advance(bluey, dt(25, 9, 0))
    assert L.go_back(fresh, dt(25, 9, 1)).notified is True      # due 25 Nov, today: treated as already notified


def test_go_back_without_a_remembered_step_uses_the_sequence(bluey):
    from dataclasses import replace
    cond = replace(bluey, step="Conditioning", step_start=dt(28, 9, 0))
    back = L.go_back(cond, dt(28, 9, 1))
    assert back.step == "Cold Crashing" and back.step_start == dt(28, 9, 1)
    ready = replace(bluey, step="Ready to drink")
    assert L.go_back(ready, dt(3, 9, 0, month=12)).step == "Conditioning"


# ---------------------------------------------------------------------------- the one fridge

def windows_for(*brews):
    return L.fridge_windows({str(i): (n, b) for i, (n, b) in enumerate(brews)})


def test_same_day_swap_is_not_a_clash(bluey, black_one):
    check = L.fridge_check(windows_for(("Bluey", bluey), ("The Black One", black_one)))
    assert check["state"] == "Free" and check["conflicts"] == []
    assert check["handovers"] == ["Bluey comes out of the fridge and The Black One goes in on Sat 28 Nov (same day, so no clash)."]


def test_overlapping_cold_crashes_clash(bluey):
    later = L.start_brew(ELVIS, dt(16), brew_days=10, crash_days=4, cond_days=5)   # crash 26 Nov - 30 Nov
    check = L.fridge_check(windows_for(("Bluey", bluey), ("Test", later)))
    assert check["state"] == "Clash"
    assert check["conflicts"][0]["text"] == ("Bluey (London Pride) and Test (Elvis Juice) both need the fridge for "
                                            "Cold Crashing between Thu 26 Nov and Sat 28 Nov.")


def test_a_beer_in_the_fridge_makes_it_in_use(bluey):
    crash = L.advance(bluey, dt(25, 9, 0))
    check = L.fridge_check(windows_for(("Bluey", crash)))
    assert check["state"] == "In use" and check["occupant"].pinter == "Bluey" and check["occupant"].end == date(2026, 11, 28)


def test_beers_before_and_after_cold_crashing_do_not_use_the_fridge(bluey):
    from dataclasses import replace
    cond = replace(bluey, step="Conditioning")
    no_crash = L.start_brew(LONDON_PRIDE, dt(15), brew_days=10, crash_days=0, cond_days=5)
    assert L.fridge_windows({"a": ("A", cond), "b": ("B", no_crash)}) == []


def test_new_brew_preview(bluey):
    windows = windows_for(("Bluey", bluey))
    state, text = L.check_new_brew(windows, date(2026, 11, 15), brew_days=10, crash_days=3)
    assert state == "Clash" and "Bluey (London Pride) has the fridge Wed 25 Nov to Sat 28 Nov" in text
    assert L.check_new_brew(windows, date(2026, 11, 15), 13, 3)[0] == "Free"          # starts on the 28th: a handover
    assert L.check_new_brew(windows, date(2026, 11, 15), 10, 0)[0] == "No Cold Crashing"
    assert L.check_new_brew(windows, date(2026, 11, 15), 10, 3, exclude_pinter="Bluey")[0] == "Free"


def test_minimum_warnings():
    assert L.minimum_warnings(ELVIS, 9, 5) == []
    assert L.minimum_warnings(ELVIS, 5, 2) == [
        "Brewing for 5 days is below the minimum of 7 days for Elvis Juice.",
        "Conditioning for 2 days is below the minimum of 3 days for Elvis Juice.",
    ]
    assert L.minimum_warnings(L.Beer("No minimums"), 1, 1) == []


# ---------------------------------------------------------------------------- the wording people see

def test_move_on_messages(bluey, black_one):
    from dataclasses import replace
    assert L.move_on_message("Bluey", bluey) == (
        "Bluey: time to move on",
        "Bluey: brewing London Pride. Move it on to Cold Crashing. Put it in the fridge with its dock attached.")
    crash = replace(black_one, step="Cold Crashing")
    assert L.move_on_message("The Black One", crash)[1] == (
        "The Black One: cold crashing Elvis Juice. Move it on to Conditioning. "
        "Take the dock off, put the hopper in, and put it back in the fridge in its tapping position.")
    no_crash = L.start_brew(LONDON_PRIDE, dt(15), brew_days=10, crash_days=0, cond_days=5)
    assert L.move_on_message("Bluey", no_crash)[1].endswith(
        "Move it on to Conditioning. Take the dock off and put it back in the fridge in its tapping position.")


def test_ready_message_includes_the_abv_when_set(black_one):
    from dataclasses import replace
    cond = replace(black_one, step="Conditioning")
    assert L.move_on_message("The Black One", cond) == (
        "The Black One is ready", "The Black One: Elvis Juice (6.5%) has finished conditioning. It is ready to drink!")
    assert "(" not in L.move_on_message("X", replace(cond, abv=0))[1]


def test_fridge_heads_up_in_the_move_on_message(bluey, black_one):
    occupied = L.FridgeWindow("Bluey", "London Pride", date(2026, 11, 25), date(2026, 11, 28), True)
    msg = L.move_on_message("The Black One", black_one, occupied)[1]
    assert msg.endswith("Heads up: the cold crash fridge is in use by Bluey (London Pride) until Sat 28 Nov.")
    assert "Heads up" not in L.move_on_message("Bluey", bluey, occupied)[1]      # not about itself
