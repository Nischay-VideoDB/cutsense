/* CutSense UI.
   Primary view: paste a video -> analysis report (techniques, recipes, comparisons).
   Secondary view: the reference library, asked in plain language. */

const $ = (sel) => document.querySelector(sel);
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};

let state = { technique: null, creator: null, q: "", clips: [] };

/* ---------- HLS playback ----------
   hls.js first, native HLS only as fallback: Chromium reports canPlayType()
   "maybe" for m3u8 and then fails to play it. */
function attachStream(videoEl, url, { loop = false, muted = false } = {}) {
  videoEl.loop = loop;
  videoEl.muted = muted;
  videoEl.playsInline = true;
  if (window.Hls && Hls.isSupported()) {
    const hls = new Hls({ maxBufferLength: 12 });
    hls.loadSource(url);
    hls.attachMedia(videoEl);
    hls.on(Hls.Events.ERROR, (_e, d) => {
      if (d.fatal && videoEl.canPlayType("application/vnd.apple.mpegurl")) videoEl.src = url;
    });
    videoEl.__hls = hls;
  } else {
    videoEl.src = url;
  }
  return videoEl;
}

function detachStream(videoEl) {
  if (videoEl.__hls) { videoEl.__hls.destroy(); videoEl.__hls = null; }
  videoEl.removeAttribute("src");
}

/* ---------- views ---------- */
function showView(name) {
  document.querySelectorAll(".view").forEach(v => v.classList.toggle("show", v.id === `view-${name}`));
  document.querySelectorAll(".tab").forEach(t => t.classList.toggle("on", t.dataset.view === name));
  if (name === "library" && !state.clips.length) { loadRails(); loadClips(); }
}

/* ---------- analyse flow ---------- */
const STAGES = ["queued", "uploading", "extracting", "detecting", "ready"];

async function analyse(url) {
  $("#analyse-error").hidden = true;
  $("#report").hidden = true;
  $("#progress").hidden = false;
  $("#analyse-btn").disabled = true;
  setProgress("queued", "sending it to the indexer");

  try {
    const started = await api(`/api/analyze?url=${encodeURIComponent(url)}`, { method: "POST" });
    if (started.state === "ready") return finishAnalysis(started);
    await poll(started.id);
  } catch (e) {
    $("#progress").hidden = true;
    $("#analyse-error").textContent = `Could not analyse that: ${e.message}`;
    $("#analyse-error").hidden = false;
  } finally {
    $("#analyse-btn").disabled = false;
  }
}

function setProgress(state, detail) {
  const idx = Math.max(0, STAGES.indexOf(state));
  $("#progress-fill").style.width = `${(idx / (STAGES.length - 1)) * 100}%`;
  const labels = {
    queued: "Queued", uploading: "Fetching the video", extracting: "Finding the cuts",
    detecting: "Reading each cut", ready: "Done", failed: "Failed",
  };
  $("#progress-text").textContent = `${labels[state] || state}${detail ? ` · ${detail}` : ""}`;
}

async function poll(id) {
  for (;;) {
    const rec = await api(`/api/analyze/${id}`);
    setProgress(rec.state, rec.stage_detail);
    if (rec.state === "ready") return finishAnalysis(rec);
    if (rec.state === "failed") throw new Error(rec.error || "analysis failed");
    await new Promise(r => setTimeout(r, 2500));
  }
}

async function finishAnalysis(rec) {
  const report = await api(`/api/report/${rec.videodb_id}`);
  $("#progress").hidden = true;
  renderReport(report);
  loadGallery();   // the new analysis belongs in the public list
}

/* ---------- public gallery ---------- */
async function loadGallery() {
  let data;
  try { data = await api("/api/gallery?limit=48"); } catch { return; }
  const el = $("#gallery");
  el.innerHTML = data.videos.map(v => `
    <button class="gcard" data-video="${v.video_id}">
      ${v.poster_clip_id
        ? `<img decoding="async" src="/api/thumb/${v.poster_clip_id}" alt=""
                onerror="this.classList.add('broken')">`
        : `<div class="placeholder">${v.techniques}</div>`}
      <div class="gmeta">
        <b>${v.title || "untitled"}</b>
        <span class="mono">${v.techniques} techniques · ${v.cuts_per_minute ?? "—"} cuts/min</span>
        <span class="gchips">${Object.entries(v.breakdown).slice(0, 3)
          .map(([k, n]) => `<i>${k} ${n}</i>`).join("")}</span>
      </div>
    </button>`).join("");
  el.querySelectorAll("[data-video]").forEach(node =>
    node.addEventListener("click", () => openReport(node.dataset.video)));
}

async function openReport(videoId) {
  $("#report").hidden = true;
  $("#progress").hidden = false;
  setProgress("detecting", "loading the report");
  try {
    renderReport(await api(`/api/report/${videoId}`));
    $("#progress").hidden = true;
    window.scrollTo({ top: $("#report").offsetTop - 70, behavior: "smooth" });
  } catch (e) {
    $("#progress").hidden = true;
    $("#analyse-error").textContent = e.message;
    $("#analyse-error").hidden = false;
  }
}

function renderReport(report) {
  const p = report.pacing;
  const el = $("#report");
  el.innerHTML = `
    <div class="report-head">
      <h2>${report.title || "your video"}</h2>
      <p class="headline">${report.headline}</p>
      ${p ? `<div class="metrics">
        ${metric(p.cuts, "cuts")}
        ${metric(p.cuts_per_minute, "cuts / min")}
        ${metric(p.avg_cut_length_s + "s", "avg shot")}
        ${metric(Math.round(p.fast_cut_share * 100) + "%", "under 1.2s")}
        ${metric(p.rhythm.rhythmic ? "yes" : "no", "rhythmic cutting")}
        ${p.rhythm.dominant_interval_s ? metric(p.rhythm.dominant_interval_s + "s", "dominant beat") : ""}
      </div>
      <div class="curve" title="cuts per 10s across the video">
        ${p.pacing_curve_cuts_per_10s.map(v => `<i style="height:${Math.min(100, v * 6)}%"></i>`).join("")}
      </div>` : ""}
    </div>
    ${report.techniques.length === 0
      ? `<p class="empty">No transitions from the current vocabulary were detected in this edit.</p>`
      : report.techniques.map(techniqueBlock).join("")}`;
  el.hidden = false;

  report.techniques.forEach(t => {
    el.querySelector(`#recipe-${t.technique}`).innerHTML =
      t.recipe ? markdown(t.recipe) : "<p class='mono'>No recipe yet.</p>";
  });
  el.querySelectorAll("[data-clip]").forEach(node => {
    node.addEventListener("click", () => openSheet(node.dataset.clip));
  });
  el.querySelectorAll("[data-reel]").forEach(btn => {
    btn.addEventListener("click", () => buildReel({ technique: btn.dataset.reel, target: "#report" }));
  });
}

const metric = (v, label) => `<div class="metric"><b>${v}</b><span>${label}</span></div>`;

function techniqueBlock(t) {
  return `
  <section class="tblock">
    <header>
      <h3>${t.label}<span class="count">${t.count} in this video</span></h3>
      <button class="ghost" data-reel="${t.technique}">Study reel of every ${t.label.toLowerCase()}</button>
    </header>
    <div class="moments">
      ${t.moments.map(m => `
        <button class="moment" data-clip="${m.clip_id}">
          <img decoding="async" src="/api/thumb/${m.clip_id}" alt=""
               onerror="this.classList.add('broken')">
          <span class="at">${m.cut_time_s.toFixed(1)}s</span>
        </button>`).join("")}
    </div>
    ${t.related_from_library.length ? `
      <div class="related">
        <div class="rel-title">Same technique elsewhere in the library</div>
        <div class="moments">
          ${t.related_from_library.map(r => `
            <button class="moment" data-clip="${r.clip_id}" title="${r.video_title}">
              <img decoding="async" src="/api/thumb/${r.clip_id}" alt="" onerror="this.classList.add('broken')">
              <span class="at">${(r.video_title || "").slice(0, 22)}</span>
            </button>`).join("")}
        </div>
      </div>` : ""}
    <details class="recipe-wrap">
      <summary>How to recreate it</summary>
      <div class="recipe" id="recipe-${t.technique}"></div>
    </details>
  </section>`;
}

/* ---------- library grid ---------- */
function cardFor(clip) {
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <div class="tag">${clip.technique_label}</div>
    ${clip.thumbnail_url
      ? `<img decoding="async" src="/api/thumb/${clip.id}" alt="" onerror="this.classList.add('broken')">`
      : `<div class="placeholder">${clip.technique}</div>`}
    <video preload="none" muted playsinline></video>
    <div class="foot">${clip.video_title || "untitled"}
      <span class="at">· ${clip.cut_time_s.toFixed(1)}s · ${Math.round(clip.confidence * 100)}%</span>
    </div>`;

  const video = card.querySelector("video");
  let armed = false;
  card.addEventListener("mouseenter", async () => {
    if (!armed) {
      armed = true;
      if (!clip.stream_url) {
        try { clip.stream_url = (await api(`/api/clips/${clip.id}/stream`)).stream_url; }
        catch { return; }
      }
      attachStream(video, clip.stream_url, { loop: true, muted: true });
    }
    card.classList.add("playing");
    video.play().catch(() => {});
  });
  card.addEventListener("mouseleave", () => { card.classList.remove("playing"); video.pause(); });
  card.addEventListener("click", () => openSheet(clip.id));
  return card;
}

function renderGrid(clips) {
  const grid = $("#grid");
  grid.innerHTML = "";
  clips.forEach(c => grid.appendChild(cardFor(c)));
  $("#empty").hidden = clips.length > 0;
  $("#reelbtn").hidden = clips.length === 0;
}

/* ---------- clip detail ---------- */
async function openSheet(id) {
  const clip = await api(`/api/clips/${id}`);
  $("#d-tag").textContent = clip.technique_label;
  $("#d-title").textContent = clip.video_title || "untitled";
  $("#d-time").textContent =
    `cut at ${clip.cut_time_s.toFixed(2)}s · clip ${clip.start_s.toFixed(1)}–${clip.end_s.toFixed(1)}s · confidence ${Math.round(clip.confidence * 100)}%`;
  $("#d-evidence").textContent = clip.evidence || "";
  const source = $("#d-source");
  source.hidden = !clip.source_url;
  if (clip.source_url) source.href = clip.source_url;
  $("#d-recipe").innerHTML = clip.recipe ? markdown(clip.recipe) : "<p class='mono'>No recipe yet.</p>";

  const player = $("#player");
  detachStream(player);
  if (clip.stream_url) attachStream(player, clip.stream_url, { loop: true });
  $("#sheet").hidden = false;
  document.body.style.overflow = "hidden";
  player.play().catch(() => {});
}

function closeSheet() {
  detachStream($("#player"));
  $("#sheet").hidden = true;
  document.body.style.overflow = "";
}

/* ---------- ask / reels / profiles / pacing ---------- */
async function ask(q) {
  ["#reel-out", "#profile-out", "#pacing-out"].forEach(s => { $(s).hidden = true; });
  $("#grid").innerHTML = `<div class="mono" style="padding:20px">thinking…</div>`;
  const data = await api(`/api/ask?q=${encodeURIComponent(q)}&limit=48`);

  $("#interpretation").hidden = false;
  $("#interpretation").innerHTML =
    `<b>${data.interpretation}</b>${data.note ? ` — <span class="dim">${data.note}</span>` : ""}`;

  if (data.plan.intent === "pacing") {
    $("#grid").innerHTML = "";
    $("#crumb").textContent = "Cutting speed";
    $("#reelbtn").hidden = true;
    renderPacing(data.videos);
    return;
  }
  if (data.plan.intent === "profile") {
    $("#grid").innerHTML = "";
    $("#crumb").textContent = "Style profile";
    $("#reelbtn").hidden = true;
    if (data.profile) renderProfile(data.profile);
    else $("#pacing-out").hidden = true;
    return;
  }

  state.clips = data.clips || [];
  renderGrid(state.clips);
  $("#crumb").textContent = `${data.count} clip${data.count === 1 ? "" : "s"}`;
  if (data.plan.intent === "reel" && state.clips.length) {
    buildReel({ q, target: "#reel-out" });
  }
}

async function buildReel({ q, technique, target }) {
  const out = $(target === "#report" ? "#reel-out" : target) || $("#reel-out");
  const host = target === "#report" ? $("#reel-out") : out;
  host.hidden = false;
  host.innerHTML = `<div class="mono">stitching a study reel…</div>`;
  if (target === "#report") showView("library");
  try {
    const params = new URLSearchParams();
    if (technique) params.set("technique", technique);
    if (q) params.set("q", q);
    params.set("limit", "12");
    const reel = await api(`/api/reels?${params}`, { method: "POST" });
    host.innerHTML = `
      <div class="reel">
        <div class="reel-meta">
          <b>${reel.name}</b>
          <span class="mono">${reel.clips} clips · ${reel.duration_s}s${reel.note ? ` · ${reel.note}` : ""}</span>
        </div>
        <video id="reel-player" controls playsinline></video>
      </div>`;
    attachStream($("#reel-player"), reel.stream_url, { loop: false });
    $("#reel-player").play().catch(() => {});
  } catch (e) {
    host.innerHTML = `<div class="failed">Could not build the reel: ${e.message}</div>`;
  }
}

function renderPacing(videos) {
  const el = $("#pacing-out");
  el.hidden = false;
  el.innerHTML = `
    <table class="ptable">
      <thead><tr><th>video</th><th>cuts/min</th><th>avg shot</th><th>under 1.2s</th><th>rhythmic</th></tr></thead>
      <tbody>${videos.map(v => `
        <tr><td>${v.title || "untitled"}</td><td class="num">${v.cuts_per_minute}</td>
        <td class="num">${v.avg_cut_length_s}s</td>
        <td class="num">${Math.round(v.fast_cut_share * 100)}%</td>
        <td class="num">${v.rhythmic ? `yes · ${v.dominant_interval_s}s` : "—"}</td></tr>`).join("")}
      </tbody>
    </table>`;
}

async function loadProfile(creator) {
  $("#grid").innerHTML = "";
  ["#reel-out", "#pacing-out"].forEach(s => { $(s).hidden = true; });
  $("#reelbtn").hidden = true;
  $("#crumb").textContent = `Style profile — ${creator}`;
  $("#profile-out").hidden = false;
  $("#profile-out").innerHTML = `<div class="mono">reading their signature…</div>`;
  try {
    renderProfile(await api(`/api/profile/creator/${encodeURIComponent(creator)}`));
  } catch (e) {
    $("#profile-out").innerHTML = `<div class="failed">${e.message}</div>`;
  }
}

function renderProfile(p) {
  const el = $("#profile-out");
  el.hidden = false;
  el.innerHTML = `
    <div class="profile">
      <h2>${p.name}</h2>
      <p class="headline">${p.signature || ""}</p>
      <div class="metrics">
        ${metric(p.videos, "videos")}
        ${metric(p.cuts, "cuts")}
        ${metric(p.cuts_per_minute, "cuts / min")}
        ${metric(p.avg_cut_length_s + "s", "avg shot")}
        ${metric(Math.round((p.fast_cut_share || 0) * 100) + "%", "under 1.2s")}
        ${metric(p.techniques_per_minute ?? "—", "techniques / min")}
      </div>
      <div class="freq">
        ${Object.entries(p.technique_frequency).map(([k, v]) =>
          `<span class="chip">${k} <b>${v}</b></span>`).join("") || "<span class='dim'>no techniques detected</span>"}
      </div>
      <div class="rel-title">Evidence</div>
      <div class="moments">
        ${p.evidence_clips.map(c => `
          <button class="moment" data-clip="${c.clip_id}" title="${c.video_title}">
            <img decoding="async" src="/api/thumb/${c.clip_id}" alt="" onerror="this.classList.add('broken')">
            <span class="at">${c.technique_label}</span>
          </button>`).join("")}
      </div>
    </div>`;
  el.querySelectorAll("[data-clip]").forEach(n =>
    n.addEventListener("click", () => openSheet(n.dataset.clip)));
}

/* ---------- minimal markdown (recipes are ours, so this only covers what we write) ---------- */
function markdown(src) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const blocks = [];
  let text = src.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) => {
    blocks.push(`<pre><code>${esc(code)}</code></pre>`);
    return ` BLOCK${blocks.length - 1} `;
  });

  text = esc(text)
    .replace(/^#### (.*)$/gm, "<h2>$1</h2>")
    .replace(/^### (.*)$/gm, "<h2>$1</h2>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/^&gt; (.*)$/gm, "<p><em>$1</em></p>")
    .replace(/^\d+\. (.*)$/gm, "<li>$1</li>")
    .replace(/^[-*] (.*)$/gm, "<li>$1</li>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  text = text.split(/\n{2,}/).map((para) => {
    const t = para.trim();
    if (!t) return "";
    if (t.startsWith("<h") || t.startsWith(" BLOCK")) return t;
    if (t.startsWith("<li>")) return `<ol>${t}</ol>`;
    return `<p>${t.replace(/\n/g, " ")}</p>`;
  }).join("\n");

  return text.replace(/ BLOCK(\d+) /g, (_m, i) => blocks[Number(i)]);
}

/* ---------- rails ---------- */
async function loadRails() {
  const [techs, creators, health] = await Promise.all([
    api("/api/techniques"), api("/api/creators"), api("/api/health"),
  ]);

  const list = $("#techlist");
  list.innerHTML = "";
  const all = document.createElement("li");
  all.innerHTML = `<span>All techniques</span>`;
  all.classList.toggle("on", !state.technique);
  all.onclick = () => select({ technique: null, creator: null, q: "" });
  list.appendChild(all);
  techs.forEach(t => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${t.label}</span><span class="n">${t.count}</span>`;
    li.classList.toggle("on", state.technique === t.id);
    li.onclick = () => select({ technique: t.id, creator: null, q: "" });
    list.appendChild(li);
  });

  const clist = $("#creatorlist");
  clist.innerHTML = "";
  creators.creators.filter(c => c.detections > 0).slice(0, 14).forEach(c => {
    const li = document.createElement("li");
    li.innerHTML = `<span>${c.creator.slice(0, 24)}</span><span class="n">${c.detections}</span>`;
    li.onclick = () => loadProfile(c.creator);
    clist.appendChild(li);
  });

  const total = Object.values(health.detections || {}).reduce((a, b) => a + b, 0);
  $("#stats").textContent = `${total} techniques · ${health.videos_total} videos indexed`;
}

async function loadClips() {
  ["#reel-out", "#profile-out", "#pacing-out", "#interpretation"].forEach(s => { $(s).hidden = true; });
  const params = new URLSearchParams();
  if (state.technique) params.set("technique", state.technique);
  params.set("limit", "48");
  $("#grid").innerHTML = `<div class="mono" style="padding:20px">loading clips…</div>`;
  const data = await api(`/api/clips?${params}`);
  state.clips = data.clips;
  renderGrid(data.clips);
  const label = state.technique ? (data.clips[0]?.technique_label || state.technique) : "Every technique";
  $("#crumb").textContent = `${label} — ${data.count} clip${data.count === 1 ? "" : "s"}`;
}

function select(next) {
  Object.assign(state, next);
  loadRails();
  loadClips();
}

/* ---------- wire up ---------- */
$("#analyse-form").addEventListener("submit", (e) => {
  e.preventDefault();
  analyse($("#analyse-url").value.trim());
});
document.querySelectorAll(".ex").forEach(b => b.addEventListener("click", () => {
  $("#analyse-url").value = b.dataset.url;
  analyse(b.dataset.url);
}));
document.querySelectorAll(".tab").forEach(t =>
  t.addEventListener("click", () => showView(t.dataset.view)));
$("#homelink").addEventListener("click", (e) => { e.preventDefault(); showView("analyse"); });
$("#searchbtn").onclick = () => ask($("#search").value.trim());
$("#search").addEventListener("keydown", e => { if (e.key === "Enter") ask($("#search").value.trim()); });
$("#reelbtn").addEventListener("click", () =>
  buildReel({ q: state.q || ($("#search").value.trim() || null), technique: state.technique, target: "#reel-out" }));
$("#close").onclick = closeSheet;
$("#sheet").addEventListener("click", e => { if (e.target === $("#sheet")) closeSheet(); });
document.addEventListener("keydown", e => { if (e.key === "Escape" && !$("#sheet").hidden) closeSheet(); });

loadRails();
loadGallery();
