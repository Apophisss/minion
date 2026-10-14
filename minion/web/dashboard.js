"use strict";
const $ = (s) => document.querySelector(s);
const api = async (path, opts = {}) => {
  const r = await fetch(path, { credentials: "same-origin", ...opts,
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).error || msg; } catch (_) {}
    throw new Error(msg);
  }
  return r.status === 204 ? null : r.json();
};
const toast = (text, ms = 3500) => {
  const t = $("#toast"); t.textContent = text; t.style.display = "block";
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.style.display = "none"), ms);
};
const fmtMem = (b) => (b == null ? "" : b > 1 << 30 ? (b / (1 << 30)).toFixed(1) + " GB" : Math.round(b / (1 << 20)) + " MB");
const thumbs = new Map();
let profiles = [];

async function loadProfiles() {
  profiles = await api("/api/profiles");
  const sel = $("#profile");
  sel.innerHTML = profiles.map((p) => `<option value="${p.name}">${p.icon || "•"} ${p.title} (${p.name})</option>`).join("");
  sel.value = profiles.some((p) => p.name === "browser") ? "browser" : profiles[0].name;
  const desc = () => { const p = profiles.find((x) => x.name === sel.value); $("#profile-desc").textContent = p ? p.description : ""; };
  sel.onchange = desc; desc();
}

function card(d) {
  const el = document.createElement("div");
  el.className = "card"; el.dataset.name = d.name;
  el.innerHTML = `
    <div class="thumb" title="Open live view"><img alt=""><div class="overlay"></div></div>
    <div class="body">
      <div class="row"><span class="name"></span><span class="badge"></span><span class="spacer"></span><span class="meta mem"></span></div>
      <div class="meta info"></div>
      <div class="row">
        <a class="btn primary open">Live view</a>
        <button class="btn toggle"></button>
        <button class="btn replay">Replay</button>
        <span class="spacer"></span>
        <button class="btn danger rm" title="Remove">✕</button>
      </div>
    </div>`;
  el.querySelector(".thumb").onclick = () => (location.href = `/view/${d.name}`);
  el.querySelector(".open").href = `/view/${d.name}`;
  el.querySelector(".replay").onclick = () => window.open(`/api/desktops/${d.name}/replay`, "_blank");
  el.querySelector(".rm").onclick = async () => {
    if (!confirm(`Remove desktop ${d.name}? Its files are deleted.`)) return;
    try { await api(`/api/desktops/${d.name}`, { method: "DELETE" }); toast(`Removed ${d.name}`); refresh(); }
    catch (e) { toast(e.message); }
  };
  return el;
}

function update(el, d) {
  el.querySelector(".name").textContent = d.name;
  const b = el.querySelector(".badge");
  b.className = "badge " + d.state; b.textContent = d.state === "paused" ? "frozen" : d.state;
  el.querySelector(".mem").textContent = fmtMem(d.memory);
  el.querySelector(".info").textContent = `${d.profile} · ${d.size}`;
  const t = el.querySelector(".toggle");
  t.textContent = d.state === "paused" ? "Thaw" : d.state === "running" ? "Freeze" : "Start";
  t.onclick = async () => {
    const op = d.state === "paused" ? "thaw" : d.state === "running" ? "freeze" : "start";
    try { await api(`/api/desktops/${d.name}/${op}`, { method: "POST", body: "{}" }); refresh(); }
    catch (e) { toast(e.message); }
  };
  el.querySelector(".overlay").textContent = d.state === "running" ? "" : d.state === "paused" ? "❄ frozen — 0% CPU" : d.state;
  el.querySelector(".overlay").style.display = d.state === "running" ? "none" : "grid";
}

async function pollThumb(name) {
  const st = thumbs.get(name);
  if (!st || st.busy) return;
  st.busy = true;
  try {
    const r = await fetch(`/api/desktops/${name}/frame?max_width=640&quality=60&since=${encodeURIComponent(st.key || "")}`, { credentials: "same-origin" });
    if (r.status === 200) {
      st.key = r.headers.get("X-Frame-Key");
      const url = URL.createObjectURL(await r.blob());
      const img = st.el.querySelector("img");
      const old = img.src; img.src = url; if (old.startsWith("blob:")) URL.revokeObjectURL(old);
    } else if (r.status === 204) st.key = r.headers.get("X-Frame-Key") || st.key;
  } catch (_) {}
  st.busy = false;
}

async function refresh() {
  let desks;
  try { desks = await api("/api/desktops?stats=1"); } catch (e) { toast(e.message); return; }
  const grid = $("#grid"); const seen = new Set();
  for (const d of desks) {
    seen.add(d.name);
    let st = thumbs.get(d.name);
    if (!st) { st = { el: card(d), key: "" }; thumbs.set(d.name, st); grid.insertBefore(st.el, $("#new-card")); }
    st.state = d.state; update(st.el, d);
  }
  for (const [name, st] of thumbs) if (!seen.has(name)) { st.el.remove(); thumbs.delete(name); }
  const running = desks.filter((d) => d.state === "running").length;
  const mem = desks.reduce((a, d) => a + (d.memory || 0), 0);
  $("#summary").textContent = `${desks.length} desktop${desks.length === 1 ? "" : "s"} · ${running} running · ${fmtMem(mem) || "0 MB"} RAM`;
}

$("#create").onclick = async () => {
  const btn = $("#create"); btn.disabled = true; btn.textContent = "Creating…";
  toast("Creating desktop… the first one of a profile may download its image.", 60000);
  try {
    const d = await api("/api/desktops", { method: "POST", body: JSON.stringify({ profile: $("#profile").value, size: $("#size").value }) });
    toast(`${d.name} is ready`); refresh();
  } catch (e) { toast(e.message, 8000); }
  btn.disabled = false; btn.textContent = "Create";
};

(async () => {
  try { const h = await api("/api/health"); $("#version").textContent = "v" + h.version + " · " + h.backend; } catch (_) {}
  await loadProfiles().catch((e) => toast(e.message));
  await refresh();
  setInterval(refresh, 5000);
  setInterval(() => { if (!document.hidden) for (const [n, st] of thumbs) if (st.state === "running") pollThumb(n); }, 1500);
})();
