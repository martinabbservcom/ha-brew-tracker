/* Brew Tracker for Pinter - dashboard card (installs itself with the integration; no other cards needed).
 *
 *   type: custom:brew-tracker-card
 *   tab: brewing        # optional: brewing (default), start, pinters or beers
 *
 * Tabs: Brewing (what is in each Pinter and when to move it on), Start brew, Pinters (add and remove), Beers (the inventory).
 * Unofficial: not made by or affiliated with Pinter.
 */
const DOMAIN = "brew_tracker";
const TABS = [["brewing", "Brewing"], ["start", "Start brew"], ["pinters", "Pinters"], ["beers", "Beers"]];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function fmt(iso) {
  if (!iso) return "";
  const d = new Date(`${String(iso).slice(0, 10)}T12:00:00`);
  const wd = d.toLocaleDateString("en-GB", { weekday: "short" });
  const mon = d.toLocaleDateString("en-GB", { month: "short" });
  return `${wd} ${String(d.getDate()).padStart(2, "0")} ${mon}`;
}

const STYLE = `
  :host { display: block; }
  ha-card { padding: 12px 16px 16px; }
  nav { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--divider-color); flex-wrap: wrap; }
  nav button { background: none; border: none; padding: 8px 14px; cursor: pointer; font: inherit; color: var(--secondary-text-color);
               border-bottom: 2px solid transparent; }
  nav button.on { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 500; }
  .pinter { border: 1px solid var(--divider-color); border-radius: 12px; padding: 12px 14px; margin-bottom: 12px; }
  .pinter h3 { margin: 0 0 2px; font-size: 1.1em; font-weight: 500; }
  .sub { color: var(--secondary-text-color); white-space: pre-line; }
  .over { color: var(--error-color, #db4437); font-weight: 500; }
  .warn { background: var(--error-color, #db4437); color: #fff; border-radius: 8px; padding: 8px 12px; margin-bottom: 12px; }
  .note { background: var(--secondary-background-color); border-radius: 8px; padding: 8px 12px; margin: 8px 0; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; }
  th, td { text-align: left; padding: 4px 8px 4px 0; border-bottom: 1px solid var(--divider-color); vertical-align: top; }
  th { font-weight: 500; color: var(--secondary-text-color); }
  .now td { font-weight: 600; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
  label { display: flex; flex-direction: column; font-size: 0.85em; color: var(--secondary-text-color); gap: 2px; }
  label.chk { flex-direction: row; align-items: center; gap: 6px; }
  input, select { font: inherit; padding: 6px 8px; border-radius: 6px; border: 1px solid var(--divider-color);
                  background: var(--card-background-color); color: var(--primary-text-color); }
  button.act { font: inherit; padding: 8px 14px; border-radius: 8px; border: 1px solid var(--primary-color); cursor: pointer;
               background: none; color: var(--primary-color); }
  button.act.main { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.act.danger { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
  button.act:disabled { opacity: 0.5; cursor: default; }
  .msg { margin-top: 10px; padding: 8px 12px; border-radius: 8px; background: var(--secondary-background-color); }
  .msg.bad { background: var(--error-color, #db4437); color: #fff; }
  .empty { color: var(--secondary-text-color); padding: 8px 0; }
  .unofficial { margin-top: 14px; font-size: 0.75em; color: var(--secondary-text-color); }
`;

class BrewTrackerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "brewing";
    this._f = { start: {}, beer: {}, newPinter: "" };
    this._msg = null;
    this._sig = null;
  }

  setConfig(config) {
    this._config = config || {};
    if (TABS.some(([k]) => k === this._config.tab)) this._tab = this._config.tab;
    this._render();
  }

  static getStubConfig() { return { tab: "brewing" }; }
  getCardSize() { return 8; }

  set hass(hass) {
    this._hass = hass;
    const data = this._collect();
    const sig = JSON.stringify(data);
    if (sig !== this._sig) {
      this._sig = sig;
      this._data = data;
      this._render();
    }
  }

  // ---------------------------------------------------------------------------------------------- data
  _collect() {
    const pinters = [];
    let beers = [], empty = [], fridge = null;
    for (const [id, s] of Object.entries(this._hass.states)) {
      if (!id.startsWith("sensor.")) continue;
      const a = s.attributes || {};
      if (a.pinter_id !== undefined) pinters.push({ entity: id, state: s.state, ...a });
      else if (Array.isArray(a.beers)) { beers = a.beers; empty = a.empty_pinters || []; }
      else if (a.conflicts !== undefined && a.capacity !== undefined) fridge = { state: s.state, ...a };
    }
    pinters.sort((x, y) => String(x.pinter).localeCompare(String(y.pinter)));
    return { pinters, beers, empty, fridge };
  }

  // Only start_brew and check_brew return a response; asking any other service for one is an error.
  async _call(service, data, confirmText, { response = false, silent = false } = {}) {
    if (confirmText && !window.confirm(confirmText)) return null;
    try {
      const msg = { type: "call_service", domain: DOMAIN, service, service_data: data };
      if (response) msg.return_response = true;
      const res = await this._hass.callWS(msg);
      if (!silent) this._msg = null;
      return (res && res.response) || {};
    } catch (e) {
      const text = (e && (e.message || e.error)) || String(e);
      if (silent) return { error: text };
      this._msg = { bad: true, text };
      this._render();
      return null;
    }
  }

  // ---------------------------------------------------------------------------------------------- render
  _render() {
    if (!this.shadowRoot) return;
    const d = this._data || { pinters: [], beers: [], empty: [], fridge: null };
    const nav = TABS.map(([k, t]) => `<button data-tab="${k}" class="${this._tab === k ? "on" : ""}">${t}</button>`).join("");
    const body = { brewing: this._brewing, start: this._start, pinters: this._pinters, beers: this._beers }[this._tab].call(this, d);
    const msg = this._msg ? `<div class="msg ${this._msg.bad ? "bad" : ""}">${esc(this._msg.text)}</div>` : "";
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card><nav>${nav}</nav>${body}${msg}
      <div class="unofficial">Brew Tracker for Pinter. Unofficial: not made by or affiliated with Pinter. A project by <a href="https://abbserv.com" target="_blank" rel="noopener">abbserv.com</a>.</div></ha-card>`;
    this._wire();
  }

  _brewing(d) {
    const warn = d.fridge && d.fridge.state === "Clash"
      ? `<div class="warn"><b>Cold crash fridge clash.</b> ${esc((d.fridge.conflicts || []).join(" "))}</div>` : "";
    const active = d.pinters.filter((p) => p.state !== "Empty");
    if (!active.length) return `${warn}<div class="empty">No beers are brewing right now. Start one from the Start brew tab.</div>`;
    return warn + active.map((p) => {
      const abv = p.abv > 0 ? ` - ${esc(p.abv)}%` : "";
      let line;
      if (p.state === "Ready to drink") line = `Ready to drink since ${fmt(p.started)}. Press Empty when it is finished.`;
      else {
        line = `${esc(p.state)} - day ${p.day} of ${p.step_days}\n`;
        if (p.days_left < 0) line += `<span class="over">OVERDUE: move it on to ${esc(p.next_step)} (was due ${esc(p.due_text)})</span>`;
        else if (p.days_left === 0) line += `<span class="over">Move it on to ${esc(p.next_step)} TODAY, ${esc(p.due_text)}</span>`;
        else line += `Move it on to ${esc(p.next_step)} on ${esc(p.due_text)} (${p.days_left} day${p.days_left === 1 ? "" : "s"})`;
      }
      const plan = (p.plan || []).length ? `<table><tr><th>Step</th><th>Days</th><th>From</th><th>Move on</th><th>What to do</th></tr>${
        p.plan.map((r) => `<tr class="${r.status === "now" ? "now" : ""}"><td>${esc(r.step)}${r.status === "now" ? " (now)" : r.status === "done" ? " (done)" : ""}</td>
          <td>${r.days}</td><td>${fmt(r.from)}</td><td>${fmt(r.to)}</td><td>${esc(r.note)}</td></tr>`).join("")}</table>
        Ready to drink: <b>${fmt(p.ready_on)}</b>` : "";
      return `<div class="pinter"><h3>${esc(p.pinter)}: ${esc(p.beer)}${abv}</h3><div class="sub">${line}</div>
        ${p.hopper_note ? `<div class="note">${esc(p.hopper_note)}</div>` : ""}${plan}
        <div class="row">
          ${p.can_go_back ? `<button class="act" data-act="back" data-pinter="${esc(p.pinter)}">Go back</button>` : ""}
          ${p.next_step ? `<button class="act main" data-act="move" data-pinter="${esc(p.pinter)}" data-step="${esc(p.state)}">Moved it on</button>` : ""}
          <button class="act danger" data-act="empty" data-pinter="${esc(p.pinter)}">Empty</button>
        </div></div>`;
    }).join("");
  }

  _start(d) {
    if (!d.beers.length) return `<div class="empty">There are no beers in the inventory yet. Add one in the Beers tab first: a brew can only be started from a saved beer.</div>`;
    if (!d.empty.length) return `<div class="empty">There is no empty Pinter. Add a Pinter in the Pinters tab, or empty one that is finished.</div>`;
    const f = this._f.start;
    if (!f.beer || !d.beers.some((b) => b.name === f.beer)) this._fillFromBeer(f, d.beers[0], d);
    if (!f.pinter || !d.empty.includes(f.pinter)) f.pinter = d.empty[0];
    const noFridge = d.fridge && d.fridge.state === "No fridge";
    const opt = (list, cur) => list.map((x) => `<option ${x === cur ? "selected" : ""}>${esc(x)}</option>`).join("");
    return `<div class="grid">
        <label>Beer (from the inventory)<select data-f="beer">${opt(d.beers.map((b) => b.name), f.beer)}</select></label>
        <label>Pinter (empty ones)<select data-f="pinter">${opt(d.empty, f.pinter)}</select></label>
        <label>Alcohol (ABV %)<input type="number" step="0.1" min="0" max="20" data-f="abv" value="${esc(f.abv)}"></label>
        <label>Brewing (days, 1-14)<input type="number" min="1" max="14" data-f="brew_days" value="${esc(f.brew_days)}"></label>
        <label>Cold Crashing (days, 0 = skip)<input type="number" min="0" max="14" data-f="crash_days" value="${noFridge ? 0 : esc(f.crash_days)}" ${noFridge ? "disabled" : ""}></label>
        <label>Conditioning (days, 1-30)<input type="number" min="1" max="30" data-f="cond_days" value="${esc(f.cond_days)}"></label>
        <label class="chk"><input type="checkbox" data-f="hopper" ${f.hopper ? "checked" : ""}> Uses a hopper (goes in when the dock comes off)</label>
        <label class="chk"><input type="checkbox" data-f="backdate" ${f.backdate ? "checked" : ""}> Already started earlier</label>
        ${f.backdate ? `<label>Started at<input type="datetime-local" data-f="started" value="${esc(f.started)}"></label>` : ""}
      </div>
      ${noFridge ? `<div class="note">No fridge is set up for Cold Crashing, so that step is skipped.</div>` : ""}
      <div class="note" id="preview">Checking...</div>
      <div class="row"><button class="act main" data-act="start">Start brew</button></div>`;
  }

  _pinters(d) {
    const rows = d.pinters.map((p) => `<tr><td>${esc(p.pinter)}</td><td>${esc(p.state)}</td><td>${esc(p.state === "Empty" ? "-" : p.beer)}</td>
      <td>${p.state === "Empty" ? `<button class="act danger" data-act="remove" data-pinter="${esc(p.pinter)}">Remove</button>` : ""}</td></tr>`).join("");
    const fr = d.fridge ? `<div class="note">Cold crash fridge: <b>${esc(d.fridge.state)}</b>${d.fridge.state === "No fridge" ? "" : ` (room for ${d.fridge.capacity}${d.fridge.conditioning_in_fridge ? ", Conditioning included" : ""})`}.
      ${(d.fridge.handovers || []).map(esc).join(" ")}</div>` : "";
    return `${d.pinters.length ? `<table><tr><th>Pinter</th><th>Step</th><th>Beer</th><th></th></tr>${rows}</table>` : `<div class="empty">No Pinters yet.</div>`}${fr}
      <div class="row"><label>New Pinter name<input data-np value="${esc(this._f.newPinter)}"></label>
      <button class="act main" data-act="add" style="align-self:flex-end">Add Pinter</button></div>`;
  }

  _beers(d) {
    const f = this._f.beer;
    const days = (a, b) => `${a ? a : "-"} / ${b ? b : "-"}`;
    const rows = d.beers.map((b) => `<tr><td>${esc(b.name)}</td><td>${b.abv > 0 ? esc(b.abv) + "%" : "-"}</td><td>${days(b.brew_min, b.brew_rec)}</td>
      <td>${days(b.cond_min, b.cond_rec)}</td><td>${b.crash}</td><td>${b.hopper ? "Yes" : "No"}</td>
      <td><button class="act" data-act="edit" data-name="${esc(b.name)}">Edit</button>
      <button class="act danger" data-act="delbeer" data-name="${esc(b.name)}">Delete</button></td></tr>`).join("");
    const num = (k, label, max) => `<label>${label}<input type="number" min="0" max="${max}" ${k === "abv" ? 'step="0.1"' : ""} data-b="${k}" value="${esc(f[k] ?? 0)}"></label>`;
    return `${d.beers.length ? `<table><tr><th>Beer</th><th>ABV</th><th>Brewing days (min / rec.)</th><th>Conditioning days (min / rec.)</th><th>Cold Crash</th><th>Hopper</th><th></th></tr>${rows}</table>` : `<div class="empty">No beers yet. Add one below.</div>`}
      <h4>Add or edit a beer</h4>
      <div class="grid"><label>Beer name<input data-b="name" value="${esc(f.name ?? "")}"></label>
        ${num("abv", "Alcohol (ABV %)", 20)}${num("brew_min", "Minimum brewing days (0 = not set)", 14)}${num("brew_rec", "Recommended brewing days", 14)}
        ${num("cond_min", "Minimum conditioning days (0 = not set)", 30)}${num("cond_rec", "Recommended conditioning days", 30)}${num("crash", "Cold Crashing days (0 = skip)", 14)}
        <label class="chk"><input type="checkbox" data-b="hopper" ${f.hopper ? "checked" : ""}> Uses a hopper</label></div>
      <div class="row"><button class="act main" data-act="savebeer">Save beer</button></div>
      <div class="sub">Saving with an existing name replaces that beer. The minimum and recommended days are on the beer's page in the Pinter store.</div>`;
  }

  // ---------------------------------------------------------------------------------------------- behaviour
  _fillFromBeer(f, beer, d) {
    if (!beer) return;
    const noFridge = d && d.fridge && d.fridge.state === "No fridge";
    Object.assign(f, {
      beer: beer.name, abv: beer.abv || 0, brew_days: beer.brew_rec || beer.brew_min || 10,
      crash_days: noFridge ? 0 : beer.crash ?? 3, cond_days: beer.cond_rec || beer.cond_min || 5, hopper: !!beer.hopper,
    });
  }

  _startData() {
    const f = this._f.start;
    const data = { pinter: f.pinter, beer: f.beer, brew_days: +f.brew_days, crash_days: +f.crash_days, cond_days: +f.cond_days,
                   abv: +f.abv, hopper: !!f.hopper };
    if (f.backdate && f.started) data.started = f.started;
    return data;
  }

  async _preview() {
    const el = this.shadowRoot.getElementById("preview");
    if (!el || this._tab !== "start") return;
    const f = this._f.start;
    const res = await this._call("check_brew", { pinter: f.pinter, beer: f.beer, brew_days: +f.brew_days, crash_days: +f.crash_days,
                                                 cond_days: +f.cond_days, ...(f.backdate && f.started ? { started: f.started } : {}) },
                                 null, { response: true, silent: true });
    const again = this.shadowRoot.getElementById("preview");
    if (again && res) {
      again.textContent = res.error || res.text || "";
      again.className = "note" + (res.error || res.state === "Clash" || res.state === "Below minimum" ? " over" : "");
    }
  }

  _wire() {
    const root = this.shadowRoot;
    root.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => { this._tab = b.dataset.tab; this._msg = null; this._render(); }));
    root.querySelectorAll("[data-f]").forEach((el) => el.addEventListener("change", () => {
      const f = this._f.start, k = el.dataset.f;
      f[k] = el.type === "checkbox" ? el.checked : el.value;
      if (k === "beer") this._fillFromBeer(f, this._data.beers.find((b) => b.name === f.beer), this._data);
      if (k === "beer" || k === "backdate") this._render(); else this._preview();
    }));
    root.querySelectorAll("[data-b]").forEach((el) => el.addEventListener("input", () => {
      this._f.beer[el.dataset.b] = el.type === "checkbox" ? el.checked : el.value;
    }));
    const np = root.querySelector("[data-np]");
    if (np) np.addEventListener("input", () => { this._f.newPinter = np.value; });
    root.querySelectorAll("[data-act]").forEach((el) => el.addEventListener("click", () => this._act(el.dataset)));
    if (this._tab === "start") this._preview();
  }

  async _act(ds) {
    const p = ds.pinter;
    switch (ds.act) {
      case "move": await this._call("move_on", { pinter: p, from_step: ds.step }, `Have you moved ${p} on to its next step?`); break;
      case "back": await this._call("go_back", { pinter: p }, `Go back to the previous step for ${p}? The earlier step's start time is put back.`); break;
      case "empty": await this._call("empty", { pinter: p }, `Mark ${p} as empty? It is ready for the next brew.`); break;
      case "remove": await this._call("remove_pinter", { pinter: p }, `Remove ${p} from the inventory?`); break;
      case "add": {
        const name = this._f.newPinter.trim();
        if (await this._call("add_pinter", { name })) this._f.newPinter = "";
        break;
      }
      case "start": {
        const res = await this._call("start_brew", this._startData(), null, { response: true });
        if (res) { this._tab = "brewing"; this._msg = { text: res.text ? `Brew started. ${res.text}` : "Brew started." }; }
        break;
      }
      case "savebeer": {
        const b = this._f.beer;
        const ok = await this._call("save_beer", { name: (b.name || "").trim(), abv: +b.abv || 0, brew_min: +b.brew_min || 0, brew_rec: +b.brew_rec || 0,
                                                    cond_min: +b.cond_min || 0, cond_rec: +b.cond_rec || 0, crash: +(b.crash ?? 3), hopper: !!b.hopper });
        if (ok) { this._f.beer = {}; this._msg = { text: `${b.name} saved.` }; }
        break;
      }
      case "edit": this._f.beer = { ...this._data.beers.find((b) => b.name === ds.name) }; break;
      case "delbeer": await this._call("delete_beer", { name: ds.name }, `Remove ${ds.name} from the beer inventory? Brews already started are not affected.`); break;
      default: return;
    }
    this._render();
  }
}

if (!customElements.get("brew-tracker-card")) customElements.define("brew-tracker-card", BrewTrackerCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "brew-tracker-card", name: "Brew Tracker for Pinter",
  description: "Track home brews in Pinter vessels: what is brewing, when to move it on, start a brew, and the beer inventory." });
