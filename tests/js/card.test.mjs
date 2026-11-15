// Browser-level checks of the dashboard card with a fake Home Assistant (run with: npm install, then npm test, in tests/js).
import { test } from "node:test";
import assert from "node:assert/strict";

// objects built inside the simulated browser have a different prototype, so compare plain copies
const plain = (x) => JSON.parse(JSON.stringify(x));
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";

const code = readFileSync(new URL("../../custom_components/brew_tracker/www/brew-tracker-card.js", import.meta.url), "utf8");

function makeCard(states) {
  const dom = new JSDOM("<!doctype html><body></body>", { runScripts: "outside-only", pretendToBeVisual: true });
  const { window } = dom;
  window.eval(code);
  const calls = [];
  window.confirm = () => true;
  const hass = {
    states,
    callWS: async (msg) => {
      calls.push(msg);
      if (msg.service === "check_brew") return { response: { state: "Free", text: "The fridge has room for this beer's Cold Crash." } };
      if (msg.service === "start_brew") return { response: { state: "Free", text: "" } };
      return {};
    },
  };
  const card = window.document.createElement("brew-tracker-card");
  window.document.body.appendChild(card);
  card.setConfig({});
  card.hass = hass;
  return { card, calls, window, hass, text: () => card.shadowRoot.textContent.replace(/\s+/g, " ") };
}

const plan = [
  { step: "Brewing", days: 10, from: "2026-11-15", to: "2026-11-25", status: "now", note: "" },
  { step: "Cold Crashing", days: 3, from: "2026-11-25", to: "2026-11-28", status: "next", note: "Fridge, dock attached" },
  { step: "Conditioning", days: 5, from: "2026-11-28", to: "2026-12-03", status: "next", note: "Dock off, fridge, tapping position" },
];

const states = () => ({
  "sensor.bluey": { state: "Brewing", attributes: { pinter: "Bluey", pinter_id: "a1", beer: "London Pride", abv: 4.7, step_days: 10, day: 1,
    days_left: 10, due_text: "Wednesday 25 November", next_step: "Cold Crashing", started: "2026-11-15T15:03:37+00:00", ready_on: "2026-12-03",
    plan, can_go_back: false, hopper_note: "", hopper: false } },
  "sensor.black_one": { state: "Brewing", attributes: { pinter: "The Black One", pinter_id: "b2", beer: "Elvis Juice", abv: 6.5, step_days: 13, day: 1,
    days_left: 13, due_text: "Saturday 28 November", next_step: "Cold Crashing", started: "2026-11-15T15:37:24+00:00", ready_on: "2026-12-06",
    plan, can_go_back: true, hopper_note: "The hopper goes in when the dock comes off.", hopper: true } },
  "sensor.red_one": { state: "Empty", attributes: { pinter: "Red One", pinter_id: "c3" } },
  "sensor.brew_tracker_beer_inventory": { state: "2", attributes: { empty_pinters: ["Red One"], beers: [
    { name: "London Pride", abv: 4.7, brew_min: 5, brew_rec: 7, cond_min: 3, cond_rec: 5, crash: 3, hopper: false },
    { name: "Elvis Juice", abv: 6.5, brew_min: 7, brew_rec: 9, cond_min: 3, cond_rec: 5, crash: 3, hopper: true } ] } },
  "sensor.brew_tracker_cold_crash_fridge": { state: "Free", attributes: { capacity: 1, conflicts: [], handovers: [], conditioning_in_fridge: false } },
});

test("the Brewing tab shows each brewing Pinter and what to do", () => {
  const { text } = makeCard(states());
  const t = text();
  assert.match(t, /Bluey: London Pride - 4\.7%/);
  assert.match(t, /The Black One: Elvis Juice - 6\.5%/);
  assert.match(t, /Move it on to Cold Crashing on Wednesday 25 November \(10 days\)/);
  assert.match(t, /The hopper goes in when the dock comes off\./);
  assert.match(t, /Ready to drink: Thu 03 Dec/);
  assert.doesNotMatch(t, /Red One/);                       // an empty Pinter is not listed on the Brewing tab
});

test("Moved it on confirms, then calls move_on for that step only, without asking for a response", async () => {
  const { card, calls } = makeCard(states());
  card.shadowRoot.querySelector('[data-act="move"][data-pinter="Bluey"]').click();
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(plain(calls.at(-1)), { type: "call_service", domain: "brew_tracker", service: "move_on",
                                    service_data: { pinter: "Bluey", from_step: "Brewing" } });
});

test("a declined confirmation does nothing", async () => {
  const { card, calls, window } = makeCard(states());
  window.confirm = () => false;
  card.shadowRoot.querySelector('[data-act="empty"][data-pinter="Bluey"]').click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(calls.filter((c) => c.service === "empty").length, 0);
});

test("Go back is only offered when there is something to undo", () => {
  const { card } = makeCard(states());
  assert.equal(card.shadowRoot.querySelectorAll('[data-act="back"]').length, 1);
  assert.equal(card.shadowRoot.querySelector('[data-act="back"]').dataset.pinter, "The Black One");
});

test("a fridge clash is shown as a warning", () => {
  const s = states();
  s["sensor.brew_tracker_cold_crash_fridge"].state = "Clash";
  s["sensor.brew_tracker_cold_crash_fridge"].attributes.conflicts = ["Bluey (London Pride) and Test (Elvis Juice) both need the fridge."];
  assert.match(makeCard(s).text(), /Cold crash fridge clash\. Bluey \(London Pride\) and Test/);
});

test("overdue steps are flagged", () => {
  const s = states();
  s["sensor.bluey"].attributes.days_left = -2;
  assert.match(makeCard(s).text(), /OVERDUE: move it on to Cold Crashing \(was due Wednesday 25 November\)/);
});

test("Start brew: pick a beer from the inventory, days fill in, the fridge is checked, and start_brew asks for a response", async () => {
  const { card, calls } = makeCard(states());
  card.shadowRoot.querySelector('[data-tab="start"]').click();
  await new Promise((r) => setTimeout(r, 10));
  const root = card.shadowRoot;
  assert.equal(root.querySelector('[data-f="beer"]').value, "London Pride");
  assert.equal(root.querySelector('[data-f="brew_days"]').value, "7");           // the recommended days
  assert.equal(root.querySelector('[data-f="cond_days"]').value, "5");
  const select = root.querySelector('[data-f="beer"]');
  select.value = "Elvis Juice";
  select.dispatchEvent(new card.ownerDocument.defaultView.Event("change"));
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(root.querySelector('[data-f="brew_days"]').value, "9");
  assert.equal(root.querySelector('[data-f="hopper"]').checked, true);
  assert.equal(root.querySelector('[data-f="abv"]').value, "6.5");
  assert.match(root.getElementById("preview").textContent, /fridge has room/);
  const check = calls.filter((c) => c.service === "check_brew").at(-1);
  assert.equal(check.return_response, true);
  assert.equal(check.service_data.pinter, "Red One");
  root.querySelector('[data-act="start"]').click();
  await new Promise((r) => setTimeout(r, 10));
  const start = calls.at(-1);
  assert.equal(start.service, "start_brew");
  assert.equal(start.return_response, true);
  assert.deepEqual(plain(start.service_data), { pinter: "Red One", beer: "Elvis Juice", brew_days: 9, crash_days: 3, cond_days: 5, abv: 6.5, hopper: true });
});

test("with no fridge set up the Cold Crashing days are forced to 0", async () => {
  const s = states();
  s["sensor.brew_tracker_cold_crash_fridge"] = { state: "No fridge", attributes: { capacity: 0, conflicts: [], handovers: [], conditioning_in_fridge: false } };
  const { card } = makeCard(s);
  card.shadowRoot.querySelector('[data-tab="start"]').click();
  await new Promise((r) => setTimeout(r, 10));
  const crash = card.shadowRoot.querySelector('[data-f="crash_days"]');
  assert.equal(crash.value, "0");
  assert.equal(crash.disabled, true);
});

test("starting is not offered without a saved beer or without an empty Pinter", async () => {
  const s = states();
  s["sensor.brew_tracker_beer_inventory"].attributes.beers = [];
  let c = makeCard(s);
  c.card.shadowRoot.querySelector('[data-tab="start"]').click();
  assert.match(c.text(), /There are no beers in the inventory yet/);
  const s2 = states();
  s2["sensor.brew_tracker_beer_inventory"].attributes.empty_pinters = [];
  c = makeCard(s2);
  c.card.shadowRoot.querySelector('[data-tab="start"]').click();
  assert.match(c.text(), /There is no empty Pinter/);
});

test("names are escaped, so a name cannot inject markup", () => {
  const s = states();
  s["sensor.bluey"].attributes.beer = '<img src=x onerror="alert(1)">';
  const { card } = makeCard(s);
  assert.equal(card.shadowRoot.querySelectorAll("img").length, 0);
});

test("Beers tab: edit loads a beer into the form, and Save sends every field", async () => {
  const { card, calls } = makeCard(states());
  card.shadowRoot.querySelector('[data-tab="beers"]').click();
  await new Promise((r) => setTimeout(r, 10));
  card.shadowRoot.querySelector('[data-act="edit"][data-name="Elvis Juice"]').click();
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(card.shadowRoot.querySelector('[data-b="name"]').value, "Elvis Juice");
  card.shadowRoot.querySelector('[data-act="savebeer"]').click();
  await new Promise((r) => setTimeout(r, 10));
  assert.deepEqual(plain(calls.at(-1)), { type: "call_service", domain: "brew_tracker", service: "save_beer",
    service_data: { name: "Elvis Juice", abv: 6.5, brew_min: 7, brew_rec: 9, cond_min: 3, cond_rec: 5, crash: 3, hopper: true } });
});
