"use strict";
const $ = (s) => document.querySelector(s);
const NAME = decodeURIComponent(location.pathname.split("/").filter(Boolean)[1] || "");
const BASE = `/api/desktops/${encodeURIComponent(NAME)}`;
const img = $("#img"), catcher = $("#catcher"), screenEl = $("#screen");
let screenW = 1280, screenH = 800, key = "", control = false, state = "running", alive = true;

const toast = (text, ms = 3000) => {
  const t = $("#toast"); t.textContent = text; t.style.display = "block";
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.style.display = "none"), ms);
};
const post = (path, body) => fetch(BASE + path, { method: "POST", credentials: "same-origin",
  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

function setStatus(kind, text) {
  $("#dot").className = "dot " + kind;
  $("#state").textContent = text;
}

// -- frames -------------------------------------------------------------------
let shownW = 1280;
function fit() {
  const stage = document.querySelector(".stage").getBoundingClientRect();
  const aspect = screenW / screenH;
  const w = Math.max(320, Math.min(stage.width - 24, (stage.height - 24) * aspect));
  shownW = w;
  img.style.width = `${Math.round(w)}px`;
  img.style.height = `${Math.round(w / aspect)}px`;
}
window.addEventListener("resize", fit);

async function frames() {
  while (alive) {
    if (state !== "running") { await sleep(1000); continue; }
    try {
      const w = Math.min(2560, Math.max(640, Math.round(shownW * (window.devicePixelRatio || 1))));
      const r = await fetch(`${BASE}/frame?since=${encodeURIComponent(key)}&wait=1500&max_width=${w}`,
        { credentials: "same-origin" });
      if (r.status === 200) {
        key = r.headers.get("X-Frame-Key") || "";
        const s = (r.headers.get("X-Screen") || "").split("x").map(Number);
        if (s.length === 2 && s[0] && (s[0] !== screenW || s[1] !== screenH || !img.style.width)) { [screenW, screenH] = s; fit(); }
        const url = URL.createObjectURL(await r.blob());
        const old = img.src; img.src = url;
        if (old.startsWith("blob:")) setTimeout(() => URL.revokeObjectURL(old), 1000);
        setStatus("live", control ? "you are in control" : "live");
      } else if (r.status === 204) {
        key = r.headers.get("X-Frame-Key") || key;
        setStatus("live", control ? "you are in control" : "live");
      } else if (r.status === 401) { setStatus("err", "unauthorized — open the link with ?token="); await sleep(3000); }
      else { setStatus("err", (await r.json().catch(() => ({}))).error || r.statusText); await sleep(1500); }
    } catch (e) { setStatus("err", "reconnecting…"); await sleep(1500); }
  }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// -- input --------------------------------------------------------------------
let queue = Promise.resolve();
const send = (ev) => { queue = queue.then(() => post("/input", ev).catch(() => {})); return queue; };
const point = (e) => {
  const r = img.getBoundingClientRect();
  return { x: Math.round(((e.clientX - r.left) / r.width) * screenW), y: Math.round(((e.clientY - r.top) / r.height) * screenH) };
};
const BUTTONS = ["left", "middle", "right"];
let lastMove = 0, pendingMove = null, moveTimer = null;

catcher.addEventListener("pointerdown", (e) => {
  if (!control) return;
  e.preventDefault(); catcher.focus(); catcher.setPointerCapture(e.pointerId);
  flushMove(); send({ type: "down", button: BUTTONS[e.button] || "left", ...point(e) });
});
catcher.addEventListener("pointerup", (e) => {
  if (!control) return;
  e.preventDefault(); flushMove(); send({ type: "up", button: BUTTONS[e.button] || "left", ...point(e) });
});
catcher.addEventListener("pointermove", (e) => {
  if (!control) return;
  pendingMove = { type: "move", ...point(e) };
  const now = performance.now();
  if (now - lastMove > 50) flushMove(); else if (!moveTimer) moveTimer = setTimeout(flushMove, 50);
});
function flushMove() {
  clearTimeout(moveTimer); moveTimer = null;
  if (pendingMove) { send(pendingMove); pendingMove = null; lastMove = performance.now(); }
}
catcher.addEventListener("contextmenu", (e) => control && e.preventDefault());
catcher.addEventListener("wheel", (e) => {
  if (!control) return;
  e.preventDefault();
  const dy = e.deltaY, dx = e.deltaX;
  const vertical = Math.abs(dy) >= Math.abs(dx);
  const d = vertical ? dy : dx;
  const amount = Math.max(1, Math.round(Math.abs(d) / 100));
  send({ type: "scroll", direction: vertical ? (d > 0 ? "down" : "up") : (d > 0 ? "right" : "left"), amount, ...point(e) });
}, { passive: false });

const KEYMAP = { Enter: "Return", Backspace: "BackSpace", Escape: "Escape", Tab: "Tab", ArrowUp: "Up",
  ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", Delete: "Delete", Insert: "Insert", Home: "Home",
  End: "End", PageUp: "Page_Up", PageDown: "Page_Down", " ": "space", CapsLock: "Caps_Lock",
  ContextMenu: "Menu", PrintScreen: "Print" };
let typeBuf = "", typeTimer = null, lastEsc = 0;
function flushType() {
  clearTimeout(typeTimer); typeTimer = null;
  if (typeBuf) { send({ type: "type", text: typeBuf }); typeBuf = ""; }
}
catcher.addEventListener("keydown", (e) => {
  if (!control) return;
  if (["Shift", "Control", "Alt", "Meta", "AltGraph", "OS"].includes(e.key)) return;
  if (e.key === "Escape") {
    const now = performance.now();
    if (now - lastEsc < 600) { e.preventDefault(); setControl(false); return; }
    lastEsc = now;
  }
  const mods = [];
  if (e.ctrlKey) mods.push("ctrl");
  if (e.altKey) mods.push("alt");
  if (e.metaKey) mods.push("super");
  let k = KEYMAP[e.key] || (e.key.length === 1 ? e.key : /^F\d{1,2}$/.test(e.key) ? e.key : null);
  if (!k) return;
  e.preventDefault();
  if (e.key.length === 1 && !mods.length) { typeBuf += e.key; clearTimeout(typeTimer); typeTimer = setTimeout(flushType, 40); return; }
  if (e.shiftKey && (k.length > 1 || mods.length)) mods.push("shift");
  flushType();
  send({ type: "key", keys: [...mods, k.length === 1 ? k.toLowerCase() : k].join("+") });
});
catcher.addEventListener("paste", (e) => {
  if (!control) return;
  e.preventDefault();
  const text = (e.clipboardData || window.clipboardData).getData("text");
  if (text) { flushType(); send({ type: "type", text }); }
});

function setControl(on) {
  control = on;
  screenEl.classList.toggle("control", on);
  $("#control").classList.toggle("on", on);
  $("#control").textContent = on ? "✋ Release control" : "🖐 Take control";
  $("#hint").textContent = on ? "You are in control · press Esc twice to release" : "Watching · click “Take control” to use mouse and keyboard";
  catcher.style.cursor = on ? "crosshair" : "default";
  if (on) catcher.focus();
}
$("#control").onclick = () => setControl(!control);
$("#paste").onclick = async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) { send({ type: "type", text }); toast(`Typed ${text.length} characters`); }
  } catch (_) { toast("Clipboard access was blocked — take control and press Ctrl+V instead"); }
};
$("#shot").onclick = () => window.open(`${BASE}/screenshot?download=1`, "_blank");
$("#replay").onclick = () => window.open(`${BASE}/replay`, "_blank");
$("#freeze").onclick = async () => {
  const op = state === "paused" ? "thaw" : "freeze";
  const r = await post("/" + op);
  if (r.ok) { state = (await r.json()).state; renderState(); toast(op === "freeze" ? "Frozen: 0% CPU. Thaw (or any agent action) resumes it." : "Running"); }
};
function renderState() {
  $("#freeze").textContent = state === "paused" ? "Thaw" : "Freeze";
  if (state === "paused") setStatus("frozen", "frozen — 0% CPU");
  else if (state !== "running") setStatus("err", state);
}

// -- desktop state + hand-off ---------------------------------------------------
async function poll() {
  while (alive) {
    try {
      const r = await fetch(`${BASE}/info`, { credentials: "same-origin" });
      if (r.ok) {
        const d = await r.json();
        $("#title").textContent = `${d.name} · ${d.profile}`;
        document.title = `${d.name} · Minion`;
        if (d.state !== state) { state = d.state; renderState(); }
      }
      const h = await fetch(`${BASE}/handoff`, { credentials: "same-origin" }).then((x) => x.json());
      const box = $("#handoff");
      if (h && !h.done) {
        if (!box.classList.contains("show")) { setControl(true); toast("The agent handed you control"); }
        $("#handoff-msg").textContent = h.message; box.classList.add("show");
      } else box.classList.remove("show");
    } catch (_) {}
    await sleep(2000);
  }
}
$("#handoff-done").onclick = async () => {
  await post("/handoff", { note: $("#handoff-note").value });
  $("#handoff").classList.remove("show"); $("#handoff-note").value = ""; setControl(false);
  toast("Handed back to the agent");
};

$("#title").textContent = NAME;
frames(); poll();
