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
  headers: { "Content-Type": "application/json", "X-Minion": "1" }, body: JSON.stringify(body || {}) });
async function call(path, body) {  // POST that throws the server's error message
  const r = await post(path, body);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const fmtSize = (n) => n == null ? "" : n < 1024 ? `${n} B` : n < 1 << 20 ? `${(n / 1024).toFixed(0)} KB`
  : n < 1 << 30 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${(n / (1 << 30)).toFixed(1)} GB`;
const fmtTime = (t) => { const d = new Date(t * 1000), now = new Date();
  return d.toDateString() === now.toDateString() ? d.toTimeString().slice(0, 5) : d.toISOString().slice(0, 10); };

// A notice with buttons, bottom right: [[label, fn], ...]
function notice(text, actions = [], ms = 12000) {
  const box = $("#notice"); $("#notice-text").textContent = text;
  const acts = $("#notice-actions"); acts.innerHTML = "";
  for (const [label, fn] of actions) {
    const b = document.createElement("button"); b.className = "btn small"; b.textContent = label;
    b.onclick = () => { box.classList.remove("show"); fn(); }; acts.appendChild(b);
  }
  box.classList.add("show");
  clearTimeout(notice._t); if (ms) notice._t = setTimeout(() => box.classList.remove("show"), ms);
}

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
  const altGr = e.getModifierState && e.getModifierState("AltGraph");
  if (e.ctrlKey && !altGr) mods.push("ctrl");
  if (e.altKey && !altGr) mods.push("alt");
  if (e.metaKey) mods.push("super");
  let k = KEYMAP[e.key] || (e.key.length === 1 ? e.key : /^F\d{1,2}$/.test(e.key) ? e.key : null);
  if (!k) return;
  e.preventDefault();
  if (e.key.length === 1 && !mods.length) { typeBuf += e.key; clearTimeout(typeTimer); typeTimer = setTimeout(flushType, 40); return; }
  if (e.shiftKey && (k.length > 1 || mods.length)) mods.push("shift");
  flushType();
  const keys = [...mods, k.length === 1 ? k.toLowerCase() : k].join("+");
  send({ type: "key", keys });
  if (/^ctrl\+(shift\+)?[cx]$/.test(keys)) setTimeout(() => copyOut(true), 300);  // copied in the desktop: here too
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
  if (on) {
    catcher.focus();
    call("/clipboard", {}).then((r) => (lastCopied = r.text)).catch(() => {});  // copy out only what changes
  }
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
document.querySelectorAll("#more .menu-items button").forEach((b) => b.addEventListener("click", () => ($("#more").open = false)));
document.addEventListener("click", (e) => { if (!$("#more").contains(e.target)) $("#more").open = false; });

// -- clipboard out, keys, open ----------------------------------------------------
let lastCopied = null;
async function copyOut(auto = false) {
  try {
    const { text } = await call("/clipboard", {});
    if (auto && (!text || text === lastCopied)) return;
    lastCopied = text;
    if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
    else {  // plain http on another host: the old way
      const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand("copy"); ta.remove();
    }
    toast(text ? `Copied ${text.length} characters from the desktop` : "The desktop's clipboard is empty");
  } catch (e) { if (!auto) toast("Couldn't copy: " + e.message); }
}
$("#copy").onclick = () => copyOut(false);
$("#keys").onchange = (e) => {
  const keys = e.target.value; e.target.selectedIndex = 0;
  if (keys) { send({ type: "key", keys }); toast(`Pressed ${keys}`, 1500); }
  if (control) catcher.focus();
};
$("#open-form").onsubmit = async (e) => {
  e.preventDefault();
  const target = $("#open").value.trim(); if (!target) return;
  toast(`Opening ${target}…`, 20000);
  try {
    const r = await call("/open", { target });
    toast(r.window ? `Opened “${r.window.title || target}”` : `Opened ${target}`); $("#open").value = "";
  } catch (err) { toast(err.message, 8000); }
};
$("#login").onclick = async () => {
  const name = (prompt("Save this desktop's sign-ins as (e.g. github, work-mail):") || "").trim().toLowerCase();
  if (!name) return;
  toast("Saving… the desktop pauses for a moment", 120000);
  try {
    const r = await call("/login", { name });
    notice(`Saved sign-in “${r.name}”. New desktops start signed in like this one: minion up --login ${r.name}`, [], 20000);
    toast("Saved", 1500);
  } catch (err) { toast(err.message, 8000); }
};

// -- files ----------------------------------------------------------------------
let folder = "~/Downloads", uploadMax = null;
const filesBox = $("#files");
const drops = () => document.querySelectorAll(".drop-target").forEach((el) => (el.textContent = folder));
async function listFolder(path) {
  try {
    const r = await fetch(`${BASE}/files?path=${encodeURIComponent(path)}`, { credentials: "same-origin" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    folder = data.shown; uploadMax = data.upload_max ?? uploadMax; drops();
    $("#files-path").textContent = data.shown;
    const parent = data.path === "/" ? null : (data.shown === "~" ? data.path : data.shown).replace(/\/[^/]+$/, "") || "/";
    const rows = [];
    if (parent && parent !== data.shown) rows.push(`<li class="dir" data-path="${esc(parent)}"><span class="n">⬆ ..</span></li>`);
    for (const e of data.entries) {
      const p = (data.shown === "/" ? "" : data.shown) + "/" + e.name;
      rows.push(e.dir
        ? `<li class="dir" data-path="${esc(p)}"><span class="n" title="${esc(e.name)}">📁 ${esc(e.name)}</span>
           <span class="acts"><a class="btn small" href="${BASE}/download?path=${encodeURIComponent(p)}" title="Download as .zip">⬇</a></span></li>`
        : `<li data-file="${esc(p)}"><span class="n" title="Download ${esc(e.name)}">📄 ${esc(e.name)}</span>
           <span class="m">${fmtSize(e.size)} · ${fmtTime(e.modified)}</span>
           <span class="acts"><a class="btn small" href="${BASE}/download?path=${encodeURIComponent(p)}" title="Download">⬇</a>
           <button class="btn small open" title="Open it in the desktop">Open</button></span></li>`);
    }
    if (!data.entries.length) rows.push(`<li class="empty">Empty folder</li>`);
    if (data.total > data.entries.length) rows.push(`<li class="empty">… and ${data.total - data.entries.length} more</li>`);
    $("#files-list").innerHTML = rows.join("");
  } catch (e) { toast(e.message, 6000); }
}
$("#files-list").onclick = (e) => {
  if (e.target.closest("a")) return;  // a download link
  const li = e.target.closest("li"); if (!li) return;
  if (li.dataset.path) return listFolder(li.dataset.path);
  if (!li.dataset.file) return;
  if (e.target.closest(".open")) {
    call("/open", { target: li.dataset.file }).then(() => toast("Opened in the desktop")).catch((err) => toast(err.message));
  } else location.href = `${BASE}/download?path=${encodeURIComponent(li.dataset.file)}`;
};
document.querySelectorAll(".files-places button").forEach((b) => (b.onclick = () => listFolder(b.dataset.path)));
function toggleFiles(show) {
  filesBox.hidden = !(show ?? filesBox.hidden);
  if (!filesBox.hidden) listFolder(folder);
  fit();
}
$("#files-btn").onclick = () => toggleFiles();
$("#files-close").onclick = () => toggleFiles(false);
$("#files-up").onclick = () => $("#files-input").click();
$("#files-input").onchange = (e) => { uploadAll([...e.target.files]); e.target.value = ""; };

function uploadOne(file, into) {
  return new Promise((resolve, reject) => {
    if (uploadMax && file.size > uploadMax)  // (the server would close the connection without reading it)
      return reject(new Error(`it's over ${Math.round(uploadMax / (1 << 20))} MB (MINION_UPLOAD_MAX_MB on the server raises the limit)`));
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/upload?path=${encodeURIComponent(into)}&name=${encodeURIComponent(file.name)}`);
    xhr.setRequestHeader("X-Minion", "1");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && toast(`Uploading ${file.name}… ${Math.round((e.loaded / e.total) * 100)}%`, 60000);
    xhr.onload = () => {
      let data = {}; try { data = JSON.parse(xhr.responseText); } catch (_) {}
      xhr.status < 300 ? resolve(data) : reject(new Error(data.error || `upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("the upload failed (connection lost)"));
    xhr.send(file);
  });
}
async function uploadAll(files) {
  if (!files.length) return;
  if (uploadMax == null)  // dropped before the Files panel was opened: learn the size limit first
    try { uploadMax = (await fetch(`${BASE}/files?path=${encodeURIComponent(folder)}`, { credentials: "same-origin" }).then((r) => r.json())).upload_max ?? 0; } catch (_) {}
  const done = [];
  for (const f of files) {
    try { done.push((await uploadOne(f, folder)).path); }
    catch (e) { toast(`${f.name}: ${e.message}`, 8000); }
  }
  if (!done.length) return;
  toast(done.length === 1 ? `Uploaded → ${done[0]}` : `Uploaded ${done.length} files → ${folder}`, 4000);
  if (!filesBox.hidden) listFolder(folder);
  const actions = done.length === 1 ? [["Open in the desktop", () => call("/open", { target: done[0] }).catch((e) => toast(e.message))]] : [];
  try {  // a file dialog waiting for it (a site's Upload button): offer to choose it there
    const wins = await fetch(`${BASE}/windows`, { credentials: "same-origin" }).then((r) => r.json());
    const top = (wins || []).find((w) => w.focused);
    if (done.length === 1 && top && /upload|open|choose|select|insert|attach|import/i.test(top.title || ""))
      actions.unshift([`Choose it in “${top.title}”`, () => call("/act", { actions: [{ action: "path", path: done[0] }] })
        .then((r) => toast(r.ok === false ? r.summary || "Couldn't choose it" : "Chosen")).catch((e) => toast(e.message))]);
  } catch (_) {}
  if (actions.length) notice(done.length === 1 ? `${done[0]} is in the desktop` : `${done.length} files are in ${folder}`, actions);
}
// Drop files anywhere on the page: they go to the folder the Files panel shows (~/Downloads at first)
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
window.addEventListener("dragenter", (e) => { if (!hasFiles(e)) return; dragDepth++; drops(); $("#stage").classList.add("dropping"); filesBox.classList.add("dropping"); });
window.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("#stage").classList.remove("dropping"); filesBox.classList.remove("dropping"); } });
window.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
window.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); dragDepth = 0;
  $("#stage").classList.remove("dropping"); filesBox.classList.remove("dropping");
  uploadAll([...e.dataTransfer.files]);
});

// Downloads finished in the desktop: offer them here
let seenDownloads = null;
async function watchDownloads() {
  while (alive) {
    await sleep(5000);
    if (state !== "running" || document.hidden) continue;
    try {
      const r = await fetch(`${BASE}/files?path=${encodeURIComponent("~/Downloads")}`, { credentials: "same-origin" });
      if (!r.ok) continue;
      const data = await r.json();
      const files = data.entries.filter((e) => !e.dir && !/\.(part|crdownload|tmp|download)$/i.test(e.name));
      const now = new Map(files.map((e) => [e.name, `${e.size}:${e.modified}`]));
      if (seenDownloads) {
        const fresh = files.filter((e) => !seenDownloads.has(e.name) && Date.now() / 1000 - e.modified < 600);
        if (fresh.length) {
          const p = `${data.shown}/${fresh[0].name}`;
          notice(`Downloaded in the desktop: ${fresh[0].name}${fresh.length > 1 ? ` (+${fresh.length - 1} more)` : ""}`,
            [["Get it", () => (location.href = `${BASE}/download?path=${encodeURIComponent(p)}`)],
             ["Show", () => { folder = data.shown; toggleFiles(true); }]]);
          if (!filesBox.hidden && folder === data.shown) listFolder(folder);
        }
      }
      seenDownloads = now;
    } catch (_) {}
  }
}
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
drops();
frames(); poll(); watchDownloads();
