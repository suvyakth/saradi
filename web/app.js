const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cap = (t) => String(t ?? "").charAt(0).toUpperCase() + String(t ?? "").slice(1);
const initial = (name) => esc(String(name || "?").trim().charAt(0).toUpperCase());
const store = {
  get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch { /* private mode */ } },
};

/* ---------- Labels and hints ---------- */
const SOURCE_LABEL = {
  live: ["Live queue data", "ok", "Based on the token that is running right now."],
  history: ["Doctor's history", "", "Based on how late this doctor has run before."],
  prior: ["Usual timings", "warn", "No live data for this doctor yet, so Saradi uses usual OPD timings."],
};
const STATE_LABEL = {
  scheduled: ["Scheduled", ""], watching: ["Waiting to leave", ""], calling: ["Calling elder", "warn"],
  retry: ["Will call again", "warn"], needs_family: ["Family alerted", "danger"], en_route: ["On the way", "ok"],
  arrived: ["At hospital", "ok"], called_in: ["With doctor", "ok"], done: ["Done", "ok"], cancelled: ["Cancelled", ""],
};
const ANSWERS = [
  ["leaving", "Okay, leaving", "Elder says they are leaving now."],
  ["already_left", "Already left", "Elder says they have already left."],
  ["unwell", "Not feeling well", "Elder says they feel unwell. The family gets an urgent alert."],
  ["call_later", "Call later", "Elder asks to be called again in 5 minutes."],
  ["confused", "Who is this?", "Elder doesn't recognise the caller. The family is alerted."],
  ["no_answer", "No answer", "Nobody picked up. Saradi tries again, then alerts the family."],
];
const BRIEF_ANSWERS = [
  ["leaving", "Okay, will be ready", "Elder agrees to be ready by the leave time."],
  ["unwell", "Not feeling well", "Elder says they feel unwell. The family gets an urgent alert."],
  ["no_answer", "No answer", "Nobody picked up the morning call."],
];
const TIPS = {
  token_now: "Tell Saradi which token the doctor is seeing right now. It sharpens the estimate.",
  patients_ahead: "Enter how many patients are waiting before this elder.",
  doctor_in: "The doctor has arrived and OPD has started.",
  doctor_out: "The doctor hasn't arrived yet. Saradi uses this to adjust the plan.",
  left: "Mark that the elder has left home.",
  arrived: "Mark that the elder has reached the hospital.",
  called_in: "Mark that the elder is now with the doctor.",
  done: "Mark the visit as finished. The wait is logged and the family gets a summary.",
  more: "Open buttons for reporting what is happening at the hospital.",
  history: "Open the log of everything Saradi has done for this visit.",
};
// What the single "next step" button does, by visit state.
const NEXT_STEP = {
  scheduled: ["left", "Left home"], watching: ["left", "Left home"], calling: ["left", "Left home"],
  retry: ["left", "Left home"], needs_family: ["left", "Left home"], en_route: ["arrived", "Arrived"],
  arrived: ["called_in", "Called in"], called_in: ["done", "Visit done"],
};

const TRACK = ["Planned", "Waiting", "Calling", "On the way", "At hospital", "With doctor", "Done"];
const TRACK_INDEX = { scheduled: 0, watching: 1, calling: 2, retry: 2, needs_family: 2, en_route: 3, arrived: 4, called_in: 5, done: 6 };

const SWITCHES = [
  ["plan", "Morning plan", "The leave time and likely-seen window when the visit is planned."],
  ["update", "Leave time changes", "If the leave time moves by 20 minutes or more."],
  ["left", "Elder has left", "When the elder heads out for the hospital."],
  ["done", "Visit summary", "How long they waited, and a Google review link."],
];
const PRESETS = {
  all: { plan: true, update: true, left: true, done: true },
  key: { plan: false, update: false, left: true, done: true },
  urgent: { plan: false, update: false, left: false, done: false },
};
const CHANNEL_LABEL = { sim: "simulated WhatsApp", telegram: "Telegram", whatsapp: "WhatsApp" };

const ICON = {
  phone: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg>`,
  arrow: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`,
  lock: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>`,
};

let snap = null;                 // latest /api/state
let lastSig = { visits: "", calls: "", messages: "" };

async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

/* ---------- Overlays that must sit above open dialogs ---------- */
const hasPopover = typeof HTMLElement.prototype.showPopover === "function";
function showTop(el) {
  if (hasPopover) { if (!el.matches(":popover-open")) el.showPopover(); } else el.hidden = false;
}
function hideTop(el) {
  if (hasPopover) { if (el.matches(":popover-open")) el.hidePopover(); } else el.hidden = true;
}

let toastTimer;
function toast(msg) {
  let el = $(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast"; el.setAttribute("role", "alert");
    if (hasPopover) el.setAttribute("popover", "manual"); else el.hidden = true;
    document.body.appendChild(el);
  }
  el.textContent = msg;
  hideTop(el); showTop(el);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => hideTop(el), 5000);
}

/* ---------- Hints: hover, keyboard focus, long-press on touch, and "hints mode" ---------- */
const tipEl = $("#tip");
if (!hasPopover) { tipEl.removeAttribute("popover"); tipEl.hidden = true; }
let tipTarget = null, hoverTimer, autoHideTimer, helpMode = false, suppressClick = false;

function placeTip(target) {
  const r = target.getBoundingClientRect(), m = 10;
  const tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
  const left = Math.max(m, Math.min(r.left + r.width / 2 - tw / 2, innerWidth - tw - m));
  let top = r.top - th - 10, below = false;
  if (top < m) { top = r.bottom + 10; below = true; }
  if (top + th > innerHeight - m) top = Math.max(m, innerHeight - th - m);
  tipEl.style.left = `${left}px`;
  tipEl.style.top = `${top}px`;
  tipEl.style.setProperty("--ax", `${Math.max(14, Math.min(r.left + r.width / 2 - left, tw - 14))}px`);
  tipEl.dataset.pos = below ? "below" : "above";
}
function showTip(target, autoHideMs = 0) {
  const text = target?.dataset.tip;
  if (!text) return;
  clearTimeout(hoverTimer); clearTimeout(autoHideTimer);
  if (tipTarget && tipTarget !== target) tipTarget.removeAttribute("aria-describedby");
  tipTarget = target;
  tipEl.textContent = text;
  target.setAttribute("aria-describedby", "tip");
  showTop(tipEl);
  placeTip(target);
  if (autoHideMs) autoHideTimer = setTimeout(hideTip, autoHideMs);
}
function hideTip() {
  clearTimeout(hoverTimer); clearTimeout(autoHideTimer);
  if (tipTarget) tipTarget.removeAttribute("aria-describedby");
  tipTarget = null;
  hideTop(tipEl);
}

document.addEventListener("pointerover", (ev) => {
  if (ev.pointerType !== "mouse") return;
  const el = ev.target.closest("[data-tip]");
  if (!el) return;
  if (el === tipTarget) return;
  clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => showTip(el), 350);
});
document.addEventListener("pointerout", (ev) => {
  if (ev.pointerType !== "mouse") return;
  const el = ev.target.closest("[data-tip]");
  if (el && !el.contains(ev.relatedTarget)) hideTip();
});
document.addEventListener("focusin", (ev) => {
  const el = ev.target.closest?.("[data-tip]");
  if (el && ev.target.matches(":focus-visible")) showTip(el);
});
document.addEventListener("focusout", hideTip);
document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hideTip(); });
window.addEventListener("scroll", hideTip, { passive: true });
window.addEventListener("resize", hideTip);

// Long-press (touch / pen) explains a control without pressing it.
let lpTimer, lpStart;
document.addEventListener("pointerdown", (ev) => {
  if (ev.pointerType === "mouse") { hideTip(); return; }
  if (!helpMode) hideTip();
  const el = ev.target.closest("[data-tip]");
  if (!el || helpMode) return;
  lpStart = { x: ev.clientX, y: ev.clientY };
  clearTimeout(lpTimer);
  lpTimer = setTimeout(() => {
    showTip(el, 4500);
    suppressClick = true;
    navigator.vibrate?.(8);
  }, 450);
});
document.addEventListener("pointermove", (ev) => {
  if (lpTimer && lpStart && Math.hypot(ev.clientX - lpStart.x, ev.clientY - lpStart.y) > 10) clearTimeout(lpTimer);
});
["pointerup", "pointercancel"].forEach((type) => document.addEventListener(type, () => {
  clearTimeout(lpTimer);
  if (suppressClick) setTimeout(() => { suppressClick = false; }, 400);
}));
document.addEventListener("contextmenu", (ev) => {
  if (matchMedia("(pointer: coarse)").matches && ev.target.closest("[data-tip]")) ev.preventDefault();
});

function setHelp(on) {
  helpMode = on;
  document.body.classList.toggle("help", on);
  $("#help-banner").hidden = !on;
  $$("[data-help-toggle]").forEach((btn) => {
    btn.setAttribute("aria-pressed", String(on));
    btn.setAttribute("aria-label", on ? "Turn hints off" : "Show hints");
  });
  hideTip();
}

// Capture phase: swallow the press and show the hint instead.
document.addEventListener("click", (ev) => {
  if (suppressClick) { suppressClick = false; ev.preventDefault(); ev.stopImmediatePropagation(); return; }
  if (!helpMode) return;
  const el = ev.target.closest("[data-tip]");
  if (!el || el.closest("[data-nohelp]")) return;
  ev.preventDefault();
  ev.stopImmediatePropagation();
  showTip(el);
}, true);

/* ---------- Tabs (phone) ---------- */
const phoneQuery = matchMedia("(max-width: 720px), (max-height: 480px) and (max-width: 960px)");
const readMessages = new Set();
function setTab(name, scroll = true) {
  document.body.dataset.tab = name;
  $$(".tab").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  store.set("saradi-tab", name);
  if (scroll) window.scrollTo({ top: 0 });
  updateBadges();
}
function updateBadges() {
  const tab = document.body.dataset.tab;
  const onPhone = phoneQuery.matches;
  const keys = $$("#messages .bubble[data-key]").map((el) => el.dataset.key);
  if (!onPhone || tab === "family") keys.forEach((k) => readMessages.add(k));
  const unread = keys.filter((k) => !readMessages.has(k)).length;
  const count = $("#count-family");
  count.hidden = unread === 0;
  count.textContent = String(unread);
  $("#dot-phone").hidden = !(onPhone && tab !== "phone" && $("#calls .ringing"));
}
phoneQuery.addEventListener("change", updateBadges);
if (["plan", "phone", "family"].includes(store.get("saradi-tab"))) setTab(store.get("saradi-tab"), false);

/* ---------- Sheets ---------- */
function openSheet(id) {
  const dialog = $(`#${id}`);
  if (id === "notify-sheet") fillNotify();
  hideTip();
  if (!dialog.open) dialog.showModal();
}
function closeSheets() { $$("dialog.sheet[open]").forEach((d) => d.close()); }
// Keep the scroll lock in step with whichever sheets are open. Watching the `open` attribute covers every way a
// sheet closes (buttons, backdrop tap, Escape, back gesture) without relying on the async `close` event.
const syncModalState = () => {
  document.body.classList.toggle("modal-open", $$("dialog.sheet[open]").length > 0);
  hideTip();
};
$$("dialog.sheet").forEach((d) => {
  new MutationObserver(syncModalState).observe(d, { attributes: true, attributeFilter: ["open"] });
  d.addEventListener("click", (ev) => {
    const r = d.getBoundingClientRect();
    if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) d.close();
  });
});

/* ---------- Family notification settings ---------- */
let notifyWho = null;
function currentFamily() {
  const fams = snap?.families || [];
  return fams.find((f) => f.phone === notifyWho) || fams[0] || null;
}
function switchRow({ key, title, text, checked, locked = false, tip }) {
  return `<label class="switch-row${locked ? " locked" : ""}" data-tip="${esc(tip || text)}">
    <span class="sw-text"><b>${esc(title)}${locked ? ` <span class="lock">${ICON.lock}Always on</span>` : ""}</b><small>${esc(text)}</small></span>
    <input type="checkbox" role="switch" ${key ? `data-pref="${key}"` : ""} ${checked ? "checked" : ""} ${locked ? "disabled" : ""}>
    <span class="sw" aria-hidden="true"></span>
  </label>`;
}
function fillNotify() {
  const fams = snap?.families || [];
  const body = $("#ns-body"), sub = $("#ns-sub"), whoWrap = $("#ns-who-wrap");
  if (!fams.length) {
    body.hidden = true; whoWrap.hidden = true;
    sub.textContent = "Add a visit first. Then you can choose what its family member hears.";
    return;
  }
  body.hidden = false;
  const f = currentFamily();
  notifyWho = f.phone;
  whoWrap.hidden = fams.length < 2;
  $("#ns-who").innerHTML = fams.map((x) => `<option value="${esc(x.phone)}"${x.phone === f.phone ? " selected" : ""}>${esc(x.name)}</option>`).join("");
  sub.textContent = `Choose what ${f.name} hears about ${f.elders.join(" and ")}. Sent by ${CHANNEL_LABEL[snap.messenger] || snap.messenger}.`;
  const p = f.prefs;
  $("#ns-switches").innerHTML =
    switchRow({ title: "Urgent alerts", text: "Elder unwell, can't be reached, or confused. Always sent.", checked: true, locked: true,
      tip: "Safety alerts can't be turned off." }) +
    SWITCHES.map(([key, title, text]) => switchRow({ key, title, text, checked: p[key] })).join("") +
    switchRow({ key: "quiet", title: "Quiet hours", text: "Skip non-urgent updates overnight.", checked: p.quiet,
      tip: "Pause non-urgent updates between two times." });
  $$("#ns-times input").forEach((i) => { i.value = p[i.dataset.pref]; });
  $("#ns-times").hidden = !p.quiet;
  $("#ns-quiet-note").hidden = !p.quiet;
  $$("[data-preset]").forEach((b) => {
    const want = PRESETS[b.dataset.preset];
    b.classList.toggle("active", Object.keys(want).every((k) => p[k] === want[k]));
  });
}
let savedTimer;
async function savePrefs(patch) {
  const f = currentFamily();
  if (!f) return;
  try {
    const res = await api("/api/prefs", { family_phone: f.phone, ...patch });
    f.prefs = res.prefs;
    $("#ns-saved").textContent = "Saved";
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { $("#ns-saved").textContent = ""; }, 1800);
  } catch (e) { toast(e.message); }
  fillNotify();
}
$("#notify-sheet").addEventListener("change", (ev) => {
  const t = ev.target;
  if (t.id === "ns-who") { notifyWho = t.value; fillNotify(); return; }
  const key = t.dataset.pref;
  if (!key) return;
  if (t.type === "checkbox") savePrefs({ [key]: t.checked });
  else if (t.value) savePrefs({ [key]: t.value });
  else fillNotify();
});

/* ---------- Rendering ---------- */
function badge([text, kind, tip]) {
  return `<span class="badge ${kind}"${tip ? ` data-tip="${esc(tip)}"` : ""}>${esc(text)}</span>`;
}

function renderTrack(state) {
  const idx = TRACK_INDEX[state];
  if (idx === undefined) return "";
  const warn = state === "needs_family" || state === "retry";
  const nodes = TRACK.map((label, i) => {
    const cls = i < idx ? "done" : i === idx ? `now${warn ? " warn" : ""}${i === TRACK.length - 1 ? " final" : ""}` : "";
    return `<li class="${cls}"><span class="dot"></span><span class="lbl">${esc(state === "needs_family" && i === idx ? "Family alerted" : label)}</span></li>`;
  }).join("");
  return `<div class="track" style="--p:${(idx / (TRACK.length - 1)) * 100}%" role="img" aria-label="Visit progress: ${esc(TRACK[idx])}"><div class="rail"><i></i></div><ol>${nodes}</ol></div>`;
}

function renderVisit(v) {
  const p = v.prediction;
  let plan = "";
  if (p) {
    const showDue = !["done", "cancelled", "calling", "needs_family", "en_route", "arrived", "called_in"].includes(v.state);
    const due = p.leave_in_min > 0 ? `in ${p.leave_in_min} min` : "now";
    const src = SOURCE_LABEL[p.source];
    plan = `
      <div class="stats">
        <div class="stat key"><div class="stat-label">Leave home at</div><div class="stat-value">${esc(p.leave_at)}</div>${showDue ? `<div class="stat-sub">${esc(due)}</div>` : ""}</div>
        <div class="stat"><div class="stat-label">Likely seen</div><div class="stat-value">${esc(p.turn_p10)} – ${esc(p.turn_p90)}</div></div>
      </div>
      <div class="basis">${badge(src)}${p.source === "prior" ? "" : `<span>${esc(p.basis)}</span>`}</div>`;
  }
  let telegram = "";
  if (v.family_link) {
    telegram = v.family_link.connected
      ? `<div class="basis">${badge(["Telegram connected", "ok"])}<span>${esc(v.family_name)} gets alerts on their phone</span></div>`
      : v.family_link.url
        ? `<div class="basis">${badge(["Not connected", "warn"])}<span><a href="${esc(v.family_link.url)}" target="_blank" rel="noopener">Open Telegram to connect ${esc(v.family_name)}</a>, then press Start</span></div>`
        : `<div class="basis">${badge(["Telegram", "warn"])}<span>Can't reach Telegram, check the bot token</span></div>`;
  }
  const active = !["done", "cancelled"].includes(v.state);
  const next = NEXT_STEP[v.state];
  const nextBtn = active && next ? `
    <button class="next" data-checkin="${next[0]}" data-id="${v.id}" data-tip="${esc(TIPS[next[0]])}">
      <span class="next-text"><small>Next step</small><b>${esc(next[1])}</b></span>${ICON.arrow}
    </button>` : "";
  const report = active ? `
    <details class="more" data-dk="more-${v.id}">
      <summary data-tip="${esc(TIPS.more)}"><span class="sum-label">Report from the hospital</span></summary>
      <div class="more-body">
        <div class="section-label">Queue</div>
        <div class="checkins">
          <span class="group"><input type="number" inputmode="numeric" min="1" placeholder="Token" aria-label="Token now running" data-input="token_now-${v.id}"><button data-checkin="token_now" data-id="${v.id}" data-tip="${esc(TIPS.token_now)}">Token running</button></span>
          <span class="group"><input type="number" inputmode="numeric" min="0" placeholder="Count" aria-label="Patients ahead" data-input="patients_ahead-${v.id}"><button data-checkin="patients_ahead" data-id="${v.id}" data-tip="${esc(TIPS.patients_ahead)}">Patients ahead</button></span>
          <button data-checkin="doctor_in" data-value="1" data-id="${v.id}" data-tip="${esc(TIPS.doctor_in)}">Doctor in</button>
          <button data-checkin="doctor_in" data-value="0" data-id="${v.id}" data-tip="${esc(TIPS.doctor_out)}">Doctor not in</button>
        </div>
        <div class="section-label">Progress</div>
        <div class="checkins">
          <button data-checkin="left" data-id="${v.id}" data-tip="${esc(TIPS.left)}">Left home</button>
          <button data-checkin="arrived" data-id="${v.id}" data-tip="${esc(TIPS.arrived)}">Arrived</button>
          <button data-checkin="called_in" data-id="${v.id}" data-tip="${esc(TIPS.called_in)}">Called in</button>
          <button data-checkin="done" data-id="${v.id}" data-tip="${esc(TIPS.done)}">Done</button>
        </div>
      </div>
    </details>` : "";
  const history = `
    <details class="more" data-dk="hist-${v.id}">
      <summary data-tip="${esc(TIPS.history)}"><span class="sum-label">History <span class="count">${v.events.length}</span></span></summary>
      <ul class="events">${v.events.map((e) => `<li><b>${esc(e.at)}</b><span>${esc(e.text)}</span></li>`).join("")}</ul>
    </details>`;
  const cls = v.state === "calling" || v.state === "retry" ? " live" : v.state === "needs_family" ? " alert" : v.state === "done" ? " done" : "";
  return `
    <article class="card visit${cls}" data-key="v${v.id}">
      <div class="visit-head">
        <div class="avatar" aria-hidden="true">${initial(v.elder_name)}</div>
        <div class="who"><strong>${esc(v.elder_name)}</strong><span>${esc(v.doctor_name)} · ${esc(v.hospital)}</span></div>
        ${badge(STATE_LABEL[v.state] || [v.state, ""])}
      </div>
      <p class="meta-line">Appointment ${esc(v.appointment)}${v.patient_token ? ` · Token ${v.patient_token}` : ""} · ${Math.round(v.travel_min)} min away · ${esc(cap(v.language))}</p>
      ${renderTrack(v.state)}
      ${plan}
      ${telegram}
      ${nextBtn}
      ${report}
      ${history}
    </article>`;
}

function renderCall(c) {
  const waiting = c.provider === "sim" && !c.response;
  const options = c.purpose === "brief" ? BRIEF_ANSWERS : ANSWERS;
  const answers = waiting ? `<div class="section-label">Answer as ${esc(c.elder_name)}</div><div class="answers">${options.map(([k, label, tip]) =>
    `<button data-call="${c.id}" data-response="${k}" data-tip="${esc(tip)}">${esc(label)}</button>`).join("")}</div>` : "";
  const label = c.purpose === "brief" && c.response === "leaving" ? "okay" : (c.response || "").replace("_", " ");
  const status = c.response ? badge([cap(label), c.response === "leaving" || c.response === "already_left" ? "ok" : "warn"])
    : badge([cap(waiting ? "ringing" : c.status), "warn"]);
  return `
    <article class="card${waiting ? " ringing" : ""}" data-key="c${c.id}">
      <div class="visit-head">
        <div class="avatar phone" aria-hidden="true">${ICON.phone}</div>
        <div class="who"><strong>${esc(c.elder_name)}</strong><span class="num">${esc(c.at)} · ${esc(c.purpose === "leave" ? "Leave now" : "Morning plan")} call</span></div>
        ${status}
      </div>
      <p class="meta-line">Attempt ${c.attempt} · spoken in ${esc(cap(c.language))}</p>
      <div class="script">“${esc(c.script)}”</div>
      ${answers}
    </article>`;
}

function renderMessage(m) {
  const key = `m${esc(m.at)}-${esc(String(m.body).length)}-${esc(String(m.body).slice(0, 24))}`;
  if (String(m.status).startsWith("muted: ")) {
    return `<div class="muted-note" data-key="${key}">Not sent, ${esc(String(m.status).slice(7))} · ${esc(m.at)}</div>`;
  }
  const note = m.status === "shown" || m.status === "sent" ? "" : ` · ${esc(m.status)}`;
  return `<div class="bubble" data-key="${key}"><span class="sender">Saradi</span>${esc(m.body)}<span class="meta">${esc(m.at)} · to ${esc(m.family_name)} · ${esc(m.channel)}${note}</span></div>`;
}

const seenKeys = new Set();
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
function animateNew(container) {
  let n = 0;
  container.querySelectorAll("[data-key]").forEach((el) => {
    if (seenKeys.has(el.dataset.key)) return;
    seenKeys.add(el.dataset.key);
    el.classList.add("enter");
    el.style.animationDelay = `${Math.min(n++, 5) * 90}ms`;
  });
}

const SPARK_COLORS = ["#7dffa8", "#4de1ff", "#b794ff", "#ffc857", "#ff5c8a"];
function celebrate(el) {
  if (!el || reduceMotion.matches) return;
  const r = el.getBoundingClientRect();
  const cx = Math.min(Math.max(r.left + r.width / 2, 20), innerWidth - 20);
  const cy = Math.min(Math.max(r.top + Math.min(r.height / 2, 160), 40), innerHeight - 40);
  for (let i = 0; i < 18; i++) {
    const sp = document.createElement("i");
    sp.className = "spark";
    const a = Math.random() * Math.PI * 2, d = 60 + Math.random() * 110;
    sp.style.cssText = `left:${cx}px;top:${cy}px;background:${SPARK_COLORS[i % SPARK_COLORS.length]};--dx:${Math.cos(a) * d}px;--dy:${Math.sin(a) * d - 40}px;--rot:${Math.random() * 720 - 360}deg`;
    document.body.appendChild(sp);
    setTimeout(() => sp.remove(), 1300);
  }
}
const lastVisitState = {};
const openDetails = new Set();
document.addEventListener("toggle", (ev) => {
  const d = ev.target;
  if (!(d instanceof HTMLDetailsElement) || !d.dataset.dk) return;
  if (d.open) openDetails.add(d.dataset.dk); else openDetails.delete(d.dataset.dk);
}, true);

function renderAll(s) {
  snap = s;
  const nowEl = $("#now");
  if (nowEl.textContent !== s.now) nowEl.textContent = s.now;
  $$(".js-now").forEach((el) => { el.textContent = s.now; });
  $("#date").textContent = s.date;
  const live = (m) => (m === "sim" ? "" : " live");
  $$(".modes").forEach((el) => {
    el.innerHTML = `<span class="mode${live(s.voice)}">Voice: ${esc(s.voice)}</span><span class="mode${live(s.messenger)}">Messages: ${esc(s.messenger)}</span>`;
  });
  $$(".speed-select").forEach((el) => { if (document.activeElement !== el) el.value = String(s.speed); });

  const visitsEl = $("#visits");
  const sig = JSON.stringify(s.visits);
  const typing = visitsEl.contains(document.activeElement) && document.activeElement.tagName === "INPUT";
  if (sig !== lastSig.visits && !typing) {
    lastSig.visits = sig;
    hideTip();
    visitsEl.innerHTML = s.visits.length ? s.visits.map(renderVisit).join("")
      : `<p class="empty">No visits yet. Add one, or load the cold-start demo.</p>`;
    visitsEl.querySelectorAll("details[data-dk]").forEach((d) => { d.open = openDetails.has(d.dataset.dk); });
    animateNew(visitsEl);
    s.visits.forEach((v) => {
      if (lastVisitState[v.id] && lastVisitState[v.id] !== "done" && v.state === "done") celebrate(visitsEl.querySelector(`[data-key="v${v.id}"]`));
      lastVisitState[v.id] = v.state;
    });
  }
  const callSig = JSON.stringify(s.calls);
  if (callSig !== lastSig.calls) {
    lastSig.calls = callSig;
    hideTip();
    $("#calls").innerHTML = s.calls.length ? s.calls.map(renderCall).join("") : `<p class="empty">No calls yet.</p>`;
    animateNew($("#calls"));
  }
  const msgSig = JSON.stringify(s.messages);
  if (msgSig !== lastSig.messages) {
    lastSig.messages = msgSig;
    $("#messages").innerHTML = s.messages.length ? s.messages.map(renderMessage).join("") : `<p class="empty">No messages yet.</p>`;
    animateNew($("#messages"));
  }
  updateBadges();
}

async function refresh() {
  try { renderAll(await api("/api/state")); } catch (e) { console.error(e); }
}

/* ---------- Actions ---------- */
document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button");
  if (!t) return;
  try {
    if (t.hasAttribute("data-help-toggle")) { setHelp(!helpMode); return; }
    if (t.hasAttribute("data-help-off")) { setHelp(false); return; }
    if (t.dataset.open) { openSheet(t.dataset.open); return; }
    if (t.hasAttribute("data-close")) { t.closest("dialog")?.close(); return; }
    if (t.classList.contains("tab")) { setTab(t.dataset.tab); return; }
    if (t.dataset.preset) { await savePrefs(PRESETS[t.dataset.preset]); return; }
    if (t.id === "cancel-form") { $("#visit-form").hidden = true; return; }
    if (t.dataset.advance) await api("/api/clock", { advance_min: Number(t.dataset.advance) });
    else if (t.dataset.action === "demo") {
      await api("/api/demo", {});
      closeSheets();
      setTab("plan");
    } else if (t.id === "toggle-form") {
      const form = $("#visit-form");
      form.hidden = !form.hidden;
      if (!form.hidden) { form.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth", block: "start" }); form.querySelector("input")?.focus({ preventScroll: true }); }
      return;
    } else if (t.dataset.call) await api(`/api/calls/${t.dataset.call}/respond`, { response: t.dataset.response });
    else if (t.dataset.checkin) {
      const kind = t.dataset.checkin, id = t.dataset.id;
      let value = t.dataset.value ?? 1;
      if (kind === "token_now" || kind === "patients_ahead") {
        const input = document.querySelector(`[data-input="${kind}-${id}"]`);
        if (!input.value) { input.focus(); input.placeholder = "Enter a number"; return; }
        value = Number(input.value);
        input.value = "";
      }
      await api(`/api/visits/${id}/checkin`, { kind, value });
    } else return;
    lastSig = { visits: "", calls: "", messages: "" };
    refresh();
  } catch (e) { toast(e.message); }
});

document.addEventListener("change", async (ev) => {
  if (!ev.target.classList.contains("speed-select")) return;
  try {
    await api("/api/clock", { speed: Number(ev.target.value) });
    refresh();
  } catch (e) { toast(e.message); }
});

$("#visit-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const err = $("#form-error");
  const data = Object.fromEntries(new FormData(ev.target).entries());
  if (!/^\d{1,2}:\d{2}$/.test(data.appointment_time || "")) {
    err.textContent = "Enter the appointment time as HH:MM, like 13:00.";
    err.hidden = false;
    return;
  }
  try {
    await api("/api/visits", data);
    err.hidden = true;
    ev.target.reset();
    ev.target.hidden = true;
    lastSig.visits = "";
    refresh();
  } catch (e) { err.textContent = e.message; err.hidden = false; }
});
$("#visit-form").addEventListener("input", () => { $("#form-error").hidden = true; });

refresh();
setInterval(refresh, 1500);
