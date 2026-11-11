// Wicked Brain dashboard - vanilla JS, no build step.
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  // ---- theme (persisted per-viewer in localStorage; safe if storage is blocked) ----
  function safeGet(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function safeSet(key, val) { try { localStorage.setItem(key, val); } catch { /* ignore */ } }

  function applyTheme() {
    const saved = safeGet("mem-theme"); // "light" | "dark" | null (system)
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    const accent = safeGet("mem-accent") || "";
    if (accent) document.documentElement.setAttribute("data-accent", accent);
    else document.documentElement.removeAttribute("data-accent");
    $("#accent-select").value = accent;
  }
  $("#theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const effectiveDark = current ? current === "dark" : prefersDark;
    safeSet("mem-theme", effectiveDark ? "light" : "dark");
    applyTheme();
  });
  $("#accent-select").addEventListener("change", (e) => {
    safeSet("mem-accent", e.target.value);
    applyTheme();
  });
  applyTheme();

  // ---- view switching ----
  function showView(name) {
    $$(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === name));
    $$(".view").forEach((el) => el.classList.toggle("active", el.id === `view-${name}`));
    if (name === "graph" && !graph3dLoaded) loadGraph3D();
    if (name === "graph" && graph3dInstance) graph3dInstance.handleResize();
    if (name === "activity") loadActivity();
    if (name === "recent") loadRecent();
    if (name === "health") loadHealth();
  }
  $$(".nav-item").forEach((el) => el.addEventListener("click", () => showView(el.dataset.view)));

  // ---- keyboard shortcut ----
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      showView("search");
      $("#search-input").focus();
    }
    if (e.key === "Escape") closeNote();
  });

  // ---- stats sidebar ----
  async function loadStats() {
    try {
      const r = await fetch("/api/stats");
      const data = await r.json();
      const rows = Object.entries(data.by_folder)
        .sort((a, b) => b[1] - a[1])
        .map(([folder, count]) => `<div class="stat-row"><span>${escapeHtml(folder)}</span><b>${count}</b></div>`)
        .join("");
      $("#stat-list").innerHTML =
        `<div class="stat-row"><span>Total notes</span><b>${data.total_notes}</b></div>` + rows;
    } catch (e) {
      $("#stat-list").innerHTML = `<div class="stat-row">Vault unavailable</div>`;
    }
    loadVaultStatus();
  }
  loadStats();

  async function loadVaultStatus() {
    try {
      const r = await fetch("/api/vault-status");
      const s = await r.json();
      const badge = $("#vault-status-badge");
      if (s.is_git_vault) {
        badge.className = "vh-badge on";
        badge.innerHTML = `<span class="dot"></span> Version history on${
          s.commit_count != null ? ` &middot; ${s.commit_count} commits` : ""
        }${s.dirty_files ? ` &middot; ${s.dirty_files} uncommitted` : ""}`;
      } else {
        badge.className = "vh-badge off";
        badge.innerHTML = `<span class="dot"></span> Version history off (run /brain-init to enable)`;
      }
    } catch (e) {
      // vault-status is a nicety, never worth surfacing an error for
    }
  }

  // ---- search ----
  let searchTimer = null;
  $("#search-input").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    if (!q) {
      $("#search-results").innerHTML = `<div class="empty-state">Type a query above to search the vault.</div>`;
      return;
    }
    searchTimer = setTimeout(() => runSearch(q), 180);
  });

  async function runSearch(q) {
    showView("search");
    $("#search-results").innerHTML = `<div class="empty-state">Searching…</div>`;
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=25`);
      const data = await r.json();
      renderResults(data.results || []);
    } catch (e) {
      $("#search-results").innerHTML = `<div class="empty-state">Search failed - is the dashboard server running against a valid vault?</div>`;
    }
  }

  function renderResults(results) {
    if (!results.length) {
      $("#search-results").innerHTML = `<div class="empty-state">No matches.</div>`;
      return;
    }
    $("#search-results").innerHTML = results
      .map(
        (r) => `
        <div class="result-item" data-path="${escapeAttr(r.path)}">
          <span class="result-title">${escapeHtml(r.title || r.path)}</span>
          <span class="result-path">${escapeHtml(r.path)}</span>
          <div class="result-snippet">${escapeHtml(r.snippet || "")}</div>
        </div>`
      )
      .join("");
    $$("#search-results .result-item").forEach((el) =>
      el.addEventListener("click", () => openNote(el.dataset.path))
    );
  }

  // ---- recent ----
  async function loadRecent() {
    $("#recent-list").innerHTML = `<div class="empty-state">Loading…</div>`;
    const r = await fetch("/api/recent?limit=40");
    const data = await r.json();
    if (!data.notes.length) {
      $("#recent-list").innerHTML = `<div class="empty-state">No notes yet.</div>`;
      return;
    }
    $("#recent-list").innerHTML = data.notes
      .map((n) => {
        const d = new Date(n.mtime * 1000);
        return `<div class="result-item" data-path="${escapeAttr(n.path)}">
          <span class="result-title">${escapeHtml(n.title)}</span>
          <span class="result-path">${escapeHtml(n.path)}</span>
          <div class="result-snippet">${d.toLocaleString()}</div>
        </div>`;
      })
      .join("");
    $$("#recent-list .result-item").forEach((el) =>
      el.addEventListener("click", () => openNote(el.dataset.path))
    );
  }

  // ---- health ----
  async function loadHealth() {
    $("#health-summary").innerHTML = "";
    $("#health-groups").innerHTML = `<div class="empty-state">Scanning…</div>`;
    const r = await fetch("/api/health");
    const data = await r.json();

    const tiles = [
      { label: "Notes scanned", num: data.total_notes ?? 0 },
      { label: "Total findings", num: data.total_issues ?? 0 },
      { label: "Auto-merge candidates", num: (data.auto_merge_candidates || []).length },
    ];
    $("#health-summary").innerHTML = tiles
      .map((t) => `<div class="stat-tile"><div class="num">${t.num}</div><div class="label">${t.label}</div></div>`)
      .join("");

    const groups = data.checks || data.by_check || null;
    let html = "";
    // run_health_check returns {checks: {...}} in some versions and a flat
    // "issues" list in others - handle both without assuming shape.
    const issueList = data.issues || data.all_issues || [];
    if (issueList.length) {
      const bySeverity = { critical: [], warning: [], info: [] };
      for (const iss of issueList) {
        const sev = (iss.severity || "info").toLowerCase();
        (bySeverity[sev] || bySeverity.info).push(iss);
      }
      for (const [sev, items] of Object.entries(bySeverity)) {
        if (!items.length) continue;
        html += `<div class="health-group"><div class="health-group-title sev-${sev}"><span class="sev-dot"></span> ${sev} (${items.length})</div>`;
        html += items
          .slice(0, 50)
          .map((i) => `<div class="health-item">${escapeHtml(i.message || i.type || "")}</div>`)
          .join("");
        html += `</div>`;
      }
    } else if (groups) {
      for (const [label, items] of Object.entries(groups)) {
        if (!items || !items.length) continue;
        html += `<div class="health-group"><div class="health-group-title sev-warning"><span class="sev-dot"></span> ${escapeHtml(label)} (${items.length})</div>`;
        html += items
          .slice(0, 50)
          .map((i) => `<div class="health-item">${escapeHtml(i.message || JSON.stringify(i))}</div>`)
          .join("");
        html += `</div>`;
      }
    }
    if (data.auto_merge_candidates && data.auto_merge_candidates.length) {
      html += `<div class="health-group"><div class="health-group-title sev-info"><span class="sev-dot"></span> Auto-merge candidates (${data.auto_merge_candidates.length})</div>`;
      html += data.auto_merge_candidates
        .map((p) => `<div class="health-item">${escapeHtml(p.retire)} &rarr; ${escapeHtml(p.canonical)} (similarity ${p.similarity})</div>`)
        .join("");
      html += `</div>`;
    }
    $("#health-groups").innerHTML = html || `<div class="empty-state">Clean bill of health.</div>`;
  }

  // ---- activity heatmap ----
  const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  // Local calendar date, not toISOString() - that converts to UTC first, which
  // silently shifts "today" to yesterday for anyone west of UTC (most of the
  // US, this vault's owner included) and would misalign every cell against
  // git log's own --date=short (the commit's local date).
  function toLocalISODate(d) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  }

  async function loadActivity() {
    $("#activity-summary").innerHTML = "";
    $("#activity-heatmap").innerHTML = `<div class="empty-state">Loading…</div>`;
    try {
      const r = await fetch("/api/activity?days=371"); // a little over a year, padded to full weeks below
      const data = await r.json();
      renderActivity(data.by_day || []);
    } catch (e) {
      $("#activity-heatmap").innerHTML = `<div class="empty-state">Activity unavailable.</div>`;
    }
  }

  function renderActivity(byDay) {
    const byDate = new Map(byDay.map((d) => [d.date, d]));
    const totalCommits = byDay.reduce((s, d) => s + d.commits, 0);
    const totalInsertions = byDay.reduce((s, d) => s + d.insertions, 0);
    const activeDays = byDay.filter((d) => d.commits > 0).length;

    $("#activity-summary").innerHTML = [
      { label: "Commits (last year)", num: totalCommits },
      { label: "Lines added", num: totalInsertions.toLocaleString() },
      { label: "Active days", num: activeDays },
    ]
      .map((t) => `<div class="stat-tile"><div class="num">${t.num}</div><div class="label">${t.label}</div></div>`)
      .join("");

    if (!totalCommits) {
      $("#activity-heatmap").innerHTML =
        `<div class="empty-state">No commit history yet - version history may not be enabled for this vault (run /brain-init), or nothing has been written yet.</div>`;
      return;
    }

    // A Sun-Sat grid, 53 weeks back, ending on the Saturday of the current week.
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const end = new Date(today);
    end.setDate(end.getDate() + (6 - end.getDay()));
    const WEEKS = 53;
    const start = new Date(end);
    start.setDate(start.getDate() - WEEKS * 7 + 1);

    const days = [];
    let max = 0;
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const iso = toLocalISODate(d);
      const entry = byDate.get(iso);
      const value = entry ? entry.insertions + entry.deletions : 0;
      if (value > max) max = value;
      days.push({ date: iso, entry, value });
    }

    function levelFor(value) {
      if (!value || !max) return 0;
      const ratio = value / max;
      if (ratio > 0.75) return 4;
      if (ratio > 0.5) return 3;
      if (ratio > 0.25) return 2;
      return 1;
    }

    const weeks = [];
    for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));

    let monthLabelsHtml = "";
    let lastMonth = null;
    weeks.forEach((week, i) => {
      const m = new Date(week[0].date).getMonth();
      if (m !== lastMonth) {
        lastMonth = m;
        monthLabelsHtml += `<div class="heatmap-month" style="grid-column:${i + 1}">${MONTH_NAMES[m]}</div>`;
      }
    });

    const gridHtml = weeks
      .map(
        (week) =>
          `<div class="heatmap-week">${week
            .map((d) => {
              const lvl = levelFor(d.value);
              const commits = d.entry ? d.entry.commits : 0;
              const ins = d.entry ? d.entry.insertions : 0;
              const notes = d.entry ? d.entry.notes_touched : 0;
              const label = commits
                ? `${commits} commit${commits === 1 ? "" : "s"}, +${ins} line${ins === 1 ? "" : "s"}, ${notes} note${notes === 1 ? "" : "s"} touched — ${d.date}`
                : `No activity — ${d.date}`;
              return `<div class="heatmap-cell" data-level="${lvl}" data-date="${d.date}" data-commits="${commits}" data-label="${escapeAttr(label)}"></div>`;
            })
            .join("")}</div>`
      )
      .join("");

    $("#activity-heatmap").innerHTML =
      `<div class="heatmap-months">${monthLabelsHtml}</div><div class="heatmap-grid">${gridHtml}</div>`;

    const tooltip = $("#activity-tooltip");
    function positionTooltip(e) {
      tooltip.style.left = `${e.clientX + 12}px`;
      tooltip.style.top = `${e.clientY + 12}px`;
    }
    $$("#activity-heatmap .heatmap-cell[data-date]").forEach((el) => {
      el.addEventListener("mouseenter", (e) => {
        tooltip.textContent = el.dataset.label;
        tooltip.classList.add("show");
        positionTooltip(e);
      });
      el.addEventListener("mousemove", positionTooltip);
      el.addEventListener("mouseleave", () => tooltip.classList.remove("show"));
      // Only wire the click for a day that had real activity - most empty
      // days have no session note, and openNote()'s 404 handling isn't
      // built to render a clean "nothing here" state for one.
      if (Number(el.dataset.commits) > 0) {
        el.addEventListener("click", () => openNote(`sessions/${el.dataset.date}.md`));
        el.classList.add("clickable");
      }
    });
  }

  // ---- 3D nebula graph ----
  let graph3dLoaded = false;
  let graph3dInstance = null;

  async function loadGraph3D() {
    graph3dLoaded = true;
    const wrap = $("#graph3d-wrap");
    const container = $("#graph3d-canvas-container");
    try {
      const data = await window.WickedBrainGraph3DData.fetchVaultGraph();
      if (!data.nodes.length) {
        wrap.querySelector(".g3d-empty")?.remove();
        const empty = document.createElement("div");
        empty.className = "g3d-empty";
        empty.textContent = "No notes to graph yet.";
        wrap.appendChild(empty);
        return;
      }
      graph3dInstance = new window.WickedBrainGraph3D(container, data);
      window.WickedBrainGraph3DUI = new window.WickedBrainGraph3DUIClass(graph3dInstance, wrap);
    } catch (e) {
      container.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "g3d-empty";
      empty.textContent = "Graph unavailable - check the dashboard server console.";
      wrap.appendChild(empty);
    }
  }

  // ---- note viewer ----
  // Exposed globally so graph3d-ui.js (a separate script/closure) can open
  // the same real note viewer from its "Open full note" inspector button.
  window.WickedBrainOpenNote = (path) => openNote(path);

  async function openNote(path) {
    const overlay = $("#note-overlay");
    overlay.classList.add("open");
    $("#note-content").innerHTML = `<div class="empty-state">Loading…</div>`;
    try {
      const r = await fetch(`/api/note/${encodeURIComponent(path)}`);
      const data = await r.json();
      if (data.error) {
        $("#note-content").innerHTML = `<div class="empty-state">${escapeHtml(data.error)}</div>`;
        return;
      }
      const bodyHtml = linkify(escapeHtml(data.body || "").trim());
      const backlinksHtml = (data.backlinks || [])
        .map((b) => `<div class="backlink-item" data-path="${escapeAttr(b)}">${escapeHtml(b)}</div>`)
        .join("") || `<div style="color:var(--text-faint);font-size:12px">No backlinks.</div>`;
      // frontmatter comes back as a parsed object (or a plain string if the
      // note's frontmatter didn't parse as YAML) - render either as text.
      const fmText =
        typeof data.frontmatter === "string"
          ? data.frontmatter
          : JSON.stringify(data.frontmatter || {}, null, 2);
      $("#note-content").innerHTML = `
        <h2>${escapeHtml(path.split("/").pop().replace(/\.md$/, ""))}</h2>
        <div class="note-meta">${escapeHtml(path)}</div>
        <div class="fm-block">${escapeHtml(fmText.trim())}</div>
        <div class="note-body">${bodyHtml}</div>
        <div class="backlinks"><h3>Backlinks</h3>${backlinksHtml}</div>
        <div class="history-section"><h3>Version history</h3><div id="history-list">Loading…</div><div id="history-diff"></div></div>
      `;
      $$("#note-content .backlink-item").forEach((el) =>
        el.addEventListener("click", () => openNote(el.dataset.path))
      );
      loadHistory(path);
    } catch (e) {
      $("#note-content").innerHTML = `<div class="empty-state">Failed to load note.</div>`;
    }
  }

  async function loadHistory(path) {
    const list = $("#history-list");
    const diffEl = $("#history-diff");
    if (!list) return;
    diffEl.innerHTML = "";
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(path)}`);
      const data = await r.json();
      const commits = data.commits || [];
      if (!commits.length) {
        list.innerHTML = `<div class="no-history">No version history for this note yet (either version history isn't enabled for this vault, or this note hasn't been committed).</div>`;
        return;
      }
      list.innerHTML = commits
        .map((c) => {
          const d = new Date(c.date);
          return `<div class="history-commit" data-hash="${escapeAttr(c.hash)}" data-path="${escapeAttr(path)}">
            <span class="msg">${escapeHtml(c.message)}</span>
            <span class="meta">${escapeHtml(c.hash.slice(0, 7))} &middot; ${d.toLocaleDateString()}</span>
          </div>`;
        })
        .join("");
      $$("#history-list .history-commit").forEach((el) =>
        el.addEventListener("click", () => showDiff(el.dataset.path, el.dataset.hash))
      );
    } catch (e) {
      list.innerHTML = `<div class="no-history">Version history unavailable.</div>`;
    }
  }

  async function showDiff(path, hash) {
    const diffEl = $("#history-diff");
    diffEl.innerHTML = `<div class="no-history">Loading diff…</div>`;
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(path)}?commit=${encodeURIComponent(hash)}`);
      const data = await r.json();
      if (data.error || !data.diff) {
        diffEl.innerHTML = `<div class="no-history">No diff available.</div>`;
        return;
      }
      const colored = escapeHtml(data.diff)
        .split("\n")
        .map((line) => {
          if (line.startsWith("+") && !line.startsWith("+++")) return `<span class="diff-add">${line}</span>`;
          if (line.startsWith("-") && !line.startsWith("---")) return `<span class="diff-del">${line}</span>`;
          return line;
        })
        .join("\n");
      diffEl.innerHTML = `
        <div class="history-diff">${colored}</div>
        <button class="revert-btn" data-path="${escapeAttr(path)}" data-hash="${escapeAttr(hash)}">Revert to this version</button>
      `;
      $(".revert-btn", diffEl).addEventListener("click", (e) =>
        revertToVersion(e.target.dataset.path, e.target.dataset.hash)
      );
    } catch (e) {
      diffEl.innerHTML = `<div class="no-history">Failed to load diff.</div>`;
    }
  }

  async function revertToVersion(path, hash) {
    const short = hash.slice(0, 7);
    if (!confirm(`Revert "${path}" to its content as of commit ${short}?\n\nThis writes that older content back as the note's current version - the version you're reverting away from stays fully recoverable in history too, this isn't destructive.`)) {
      return;
    }
    const diffEl = $("#history-diff");
    diffEl.innerHTML = `<div class="no-history">Reverting…</div>`;
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(path)}?commit=${encodeURIComponent(hash)}`, {
        method: "POST",
      });
      const data = await r.json();
      if (!r.ok) {
        diffEl.innerHTML = `<div class="no-history">Revert failed: ${escapeHtml(data.detail || "unknown error")}</div>`;
        return;
      }
      // Reload the note (fresh content) and its history (the new revert commit).
      await openNote(path);
    } catch (e) {
      diffEl.innerHTML = `<div class="no-history">Revert failed.</div>`;
    }
  }
  function closeNote() {
    $("#note-overlay").classList.remove("open");
  }
  $("#note-close").addEventListener("click", closeNote);
  $("#note-overlay").addEventListener("click", (e) => {
    if (e.target.id === "note-overlay") closeNote();
  });

  // ---- helpers ----
  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function escapeAttr(s) {
    return escapeHtml(s);
  }
  function linkify(html) {
    // [[wikilink]] and [[wikilink|alias]] -> clickable spans (note titles, not full paths)
    return html.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (_, target, alias) => {
      const label = alias || target;
      return `<a href="#" data-wikilink="${escapeAttr(target.trim())}">${escapeHtml(label)}</a>`;
    });
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-wikilink]");
    if (a) {
      e.preventDefault();
      // Best-effort: search by title since we only have the bare wikilink target here.
      runSearch(a.dataset.wikilink);
    }
  });

  // graph3d.js owns its own resize listener (it needs the live THREE.js
  // camera/renderer, not a full re-fetch+rebuild) - nothing to do here.
})();
