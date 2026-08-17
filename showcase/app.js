(() => {
  const data = window.CUTSENSE_PREPARED_DATA;
  const app = document.querySelector("#app");
  const bySlug = new Map(data.videos.map((video) => [video.slug, video]));
  const byId = new Map(data.clips.map((clip) => [clip.id, clip]));

  const escape = (value) => String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;"
  })[character]);
  const timestamp = (seconds) => {
    const whole = Math.round(seconds);
    return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
  };
  const route = (path) => {
    history.pushState({}, "", path);
    render();
  };
  const videoFor = (clip) => bySlug.get(clip.video);
  const originalAtMoment = (video, seconds) => {
    const url = new URL(video.sourceUrl);
    url.searchParams.set("t", `${Math.floor(seconds)}s`);
    return url.href;
  };
  const provenance = () => `<p class="provenance">${escape(data.provenance.label)}</p>`;

  function videoCard(video) {
    return `<a class="video-card" href="/video/${video.slug}" data-route>
      <img src="${escape(video.thumbnailUrl)}" alt="Cached VideoDB thumbnail from ${escape(video.title)}" referrerpolicy="no-referrer">
      <div><h3>${escape(video.title)}</h3><p>${video.techniqueTotal} retained detections · ${video.durationS}s source</p></div>
    </a>`;
  }

  function home() {
    app.innerHTML = `<section>
      <p class="eyebrow">Video editing technique archive</p>
      <h1>See how the cut works.</h1>
      <p class="lede">CutSense keeps the useful part of an edit: its pacing, transition evidence, and reconstruction notes. This public demo is a fixed, read-only view of cached VideoDB-backed catalog data.</p>
      ${provenance()}
      <div class="section-head"><h2>Prepared reports</h2><p>Choose a retained analysis.</p></div>
      <div class="gallery">${data.videos.map(videoCard).join("")}</div>
      <div class="notice"><strong>Prepared data only.</strong><p>Uploading, fresh analysis, live VideoDB search, clip generation, reels, and local operator jobs are unavailable in this public Vercel build. The original operator workflow remains local to this repository.</p></div>
    </section>`;
  }

  function momentCard(clip) {
    return `<a class="moment" href="/clip/${clip.id}" data-route>
      <img src="${escape(clip.thumbnailUrl)}" alt="Cached thumbnail for ${escape(clip.label)} at ${timestamp(clip.cutS)}" referrerpolicy="no-referrer">
      <span>${escape(clip.label)} · ${timestamp(clip.cutS)}</span>
    </a>`;
  }

  function report(slug) {
    const video = bySlug.get(slug);
    if (!video || !video.report) return notFound("That prepared report is not available.");
    const reportData = video.report;
    const metrics = [
      [reportData.pacing.cuts, "cached shot boundaries"],
      [`${reportData.pacing.cutsPerMinute}`, "cuts / min"],
      [`${reportData.pacing.averageShotS}s`, "average shot"],
      [`${reportData.pacing.fastCutShare}%`, "cuts at or under 1.2s"]
    ];
    const sections = reportData.techniqueSections.map((section) => {
      const clips = data.clips.filter((clip) => clip.video === video.slug && clip.technique === section.id);
      return `<section class="technique-section">
        <div class="technique-head"><h2>${escape(section.label)}</h2><span class="count">${section.count} retained</span></div>
        <p class="review">Review status: ${escape(section.review)}</p>
        <div class="moment-row">${clips.length ? clips.map(momentCard).join("") : "<p class=\"mono\">No prepared thumbnail selected for this section.</p>"}</div>
        <p class="recipe"><strong>Recipe:</strong> ${escape(data.recipes[section.id])}</p>
      </section>`;
    }).join("");
    app.innerHTML = `<a class="back" href="/" data-route>← prepared reports</a>
      <section class="report-top">
        <div><p class="eyebrow">Cached report</p><h1>${escape(video.title)}</h1><p class="lede">${escape(reportData.headline)}</p>${provenance()}</div>
        <aside class="report-card"><strong>VideoDB-backed provenance</strong><p>Video ID ${escape(video.videoId)} · cached detection records and thumbnail URLs from ${escape(data.provenance.source)}. No fresh query or render is issued here.</p></aside>
      </section>
      <section><div class="section-head"><h2>Pacing</h2><p>Calculated from the retained shot-boundary timestamps.</p></div>
        <div class="metrics">${metrics.map(([value, label]) => `<div class="metric"><b>${escape(value)}</b><span>${escape(label)}</span></div>`).join("")}</div>
        <div class="curve" aria-label="Cuts per ten seconds">${reportData.pacing.curve.map((value) => `<i style="height:${Math.max(8, value * 8)}%"></i>`).join("")}</div>
        <p class="curve-label">The historical measurement does not classify this edit as rhythmic; the strongest cached 10-second window is 10.27 cuts.</p>
      </section>
      <section><div class="section-head"><h2>Techniques and evidence</h2><p>Open a prepared moment for its evidence record.</p></div>${sections}</section>
      <section class="study-unavailable"><strong>Prepared study reel unavailable.</strong> No durable VideoDB study-reel stream URL is included in the tracked snapshot. This public build will not create one.</section>`;
  }

  function library() {
    const techniques = [...new Set(data.clips.map((clip) => clip.technique))];
    app.innerHTML = `<section><p class="eyebrow">Prepared library</p><h1>Browse retained moments.</h1><p class="lede">Filter a small, fixed showcase subset by technique or search its cached evidence. “VideoDB cached” refers to the provenance of these records, not a query made by this page.</p>${provenance()}
      <div class="section-head"><h2>Moment library</h2><p id="result-count"></p></div>
      <div class="toolbar"><input id="library-search" type="search" placeholder="Search technique, title, or evidence" aria-label="Search prepared library"><button class="filter active" data-filter="all">All</button>${techniques.map((technique) => `<button class="filter" data-filter="${escape(technique)}">${escape(data.clips.find((clip) => clip.technique === technique).label)}</button>`).join("")}</div>
      <div class="clip-grid" id="clip-grid"></div></section>`;
    const grid = app.querySelector("#clip-grid");
    const count = app.querySelector("#result-count");
    const search = app.querySelector("#library-search");
    let filter = "all";
    function draw() {
      const needle = search.value.trim().toLowerCase();
      const clips = data.clips.filter((clip) => {
        const haystack = `${clip.label} ${clip.evidence} ${videoFor(clip).title}`.toLowerCase();
        return (filter === "all" || clip.technique === filter) && (!needle || haystack.includes(needle));
      });
      count.textContent = `${clips.length} prepared moments`;
      grid.innerHTML = clips.length ? clips.map((clip) => `<a class="clip-card" href="/clip/${clip.id}" data-route><div class="image"><img src="${escape(clip.thumbnailUrl)}" alt="Cached VideoDB thumbnail for ${escape(clip.label)}" referrerpolicy="no-referrer"></div><div class="content"><div class="badges"><span class="badge tech">${escape(clip.label)}</span><span class="badge">VideoDB cached</span><span class="badge">${timestamp(clip.cutS)}</span><span class="badge">${escape(clip.verified)}</span></div><h3>${escape(videoFor(clip).title)}</h3><p>${escape(clip.evidence)}</p></div></a>`).join("") : "<p class=\"empty\">No prepared moments match this filter.</p>";
    }
    app.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
      filter = button.dataset.filter;
      app.querySelectorAll("[data-filter]").forEach((other) => other.classList.toggle("active", other === button));
      draw();
    }));
    search.addEventListener("input", draw);
    draw();
  }

  function clip(id) {
    const selected = byId.get(id);
    if (!selected) return notFound("That prepared moment is not available.");
    const video = videoFor(selected);
    const related = data.clips.filter((candidate) => candidate.technique === selected.technique && candidate.id !== selected.id).slice(0, 3);
    app.innerHTML = `<a class="back" href="/library" data-route>← prepared library</a>
      <section class="moment-layout"><div><div class="moment-poster"><img src="${escape(selected.thumbnailUrl)}" alt="Cached thumbnail for ${escape(selected.label)} at ${timestamp(selected.cutS)}" referrerpolicy="no-referrer"></div>
        <div class="unavailable"><strong>Corresponding VideoDB clip unavailable in this demo.</strong><br>The tracked snapshot stores a cached thumbnail and detection evidence, but no durable stream URL. Generating a new clip would be paid work and is disabled here.</div>
        <a class="source-link" href="${escape(originalAtMoment(video, selected.cutS))}" target="_blank" rel="noreferrer">Open original source around ${timestamp(selected.cutS)} ↗</a></div>
        <aside class="detail"><p class="eyebrow">Prepared moment</p><h2>${escape(selected.label)}</h2><dl><dt>Source</dt><dd>${escape(video.title)}</dd><dt>Window</dt><dd>${timestamp(selected.startS)} - ${timestamp(selected.endS)}</dd><dt>Cut</dt><dd>${timestamp(selected.cutS)}</dd><dt>Confidence</dt><dd>${Math.round(selected.confidence * 100)}%</dd><dt>Review</dt><dd>${escape(selected.verified)}</dd><dt>Evidence</dt><dd>${escape(selected.evidence)}</dd></dl><p class="provenance">Cached VideoDB thumbnail + retained detection record</p></aside></section>
      <section><div class="section-head"><h2>Related retained moments</h2><p>Same technique, from the prepared library.</p></div><div class="moment-row">${related.map(momentCard).join("") || "<p class=\"mono\">No related prepared moments selected.</p>"}</div></section>`;
  }

  function notFound(message) {
    app.innerHTML = `<section><p class="eyebrow">Prepared archive</p><h1>Nothing here yet.</h1><p class="lede">${escape(message)}</p><a class="source-link" href="/" data-route>Return to prepared reports</a></section>`;
  }

  function render() {
    const path = location.pathname.replace(/\/+$/, "") || "/";
    document.querySelectorAll("nav a[data-route]").forEach((link) => link.removeAttribute("aria-current"));
    if (path === "/") { document.querySelector('nav a[href="/"]').setAttribute("aria-current", "page"); home(); }
    else if (path === "/library") { document.querySelector('nav a[href="/library"]').setAttribute("aria-current", "page"); library(); }
    else if (path.startsWith("/video/")) report(decodeURIComponent(path.slice(7)));
    else if (path.startsWith("/clip/")) clip(decodeURIComponent(path.slice(6)));
    else notFound("This deep link does not match the prepared CutSense archive.");
    app.focus({ preventScroll: true });
  }

  document.addEventListener("click", (event) => {
    const link = event.target.closest("[data-route]");
    if (!link || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    route(link.getAttribute("href"));
  });
  window.addEventListener("popstate", render);
  render();
})();
