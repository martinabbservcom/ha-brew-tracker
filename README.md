# Brew Tracker for Pinter

> **Status: early development. Not ready to install yet.**

A Home Assistant integration for keeping track of home brews in [Pinter](https://pinter.co.uk) brewing vessels:
which Pinter has which beer in it, what step it is on, which day and date to move it on, and a notification to your
phones when it is time.

**Unofficial.** This is a community project. It is not made by, affiliated with or endorsed by Pinter. "Pinter" is
their name; no Pinter logos, text or images are used here. The Pinter itself has no connection to Home Assistant, so
this tracks the dates and steps you give it, it does not read anything from the vessel.

## What it will do

- Any number of Pinters, each with a name, and a beer inventory you fill in (ABV, minimum and recommended brewing and
  conditioning days, Cold Crashing days, whether it uses a hopper).
- Start a brew by picking a beer and an empty Pinter. The days fill in from the beer and can be adjusted.
- Steps: Brewing, then Cold Crashing (optional, in the fridge with the dock attached), then Conditioning (dock off, the
  hopper goes in if the beer has one, back in the fridge in its tapping position), then Ready to drink.
- Notifications to the phones or notify services you choose, on the day each move is due, saying which Pinter, which beer and
  the step to move it on to, with a "Done, I moved it" button.
- One Cold Crashing fridge: a warning if two beers' Cold Crash dates overlap.
- Go back (undo) a move, with a confirmation.
- A card that installs with the integration.

## Install (when released)

1. In HACS, add this repository as a custom repository (category: Integration) and install it.
2. Restart Home Assistant, then add the integration under Settings, Devices and services.

## Support the project

It is free and open source. If it is useful to you, a donation is a welcome thank-you (link coming soon).

## Licence

MIT. See [LICENSE](LICENSE).
