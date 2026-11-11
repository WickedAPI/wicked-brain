// graph3d-data.js - adapts /api/graph's real vault data into the shape
// graph3d.js expects, and computes every "advanced" metric (PageRank, 3D
// layout, hub flag) FOR REAL from actual note connectivity - nothing here
// is placeholder/demo data. There is no "opened count" anywhere in this
// vault, so unlike the original Obsidian-plugin reference this mimics,
// that metric is simply not offered - never fabricated to fill a slot.
(() => {
  "use strict";

  // One cluster per note type, plus a catch-all for vault-surface files
  // (index.md, CRITICAL_FACTS.md, _CLAUDE.md/AGENTS.md) which have no
  // `type:` frontmatter at all (references/ai-first-rules.md's documented
  // exception) - same order/hues as the 2D graph's TYPE_COLORS so the two
  // views read as the same vault.
  const CLUSTER_ORDER = ["project", "entity", "concept", "session", "adr", "conflict", ""];
  const CLUSTER_NAMES = {
    project: "Projects", entity: "Entities", concept: "Concepts",
    session: "Sessions", adr: "Decisions", conflict: "Conflicts", "": "Vault",
  };

  function clusterIndex(type) {
    const i = CLUSTER_ORDER.indexOf(type || "");
    return i === -1 ? CLUSTER_ORDER.length - 1 : i;
  }

  // Real PageRank via standard power iteration over the vault's actual
  // wikilink edges - same algorithm any graph library uses, just run here
  // client-side since the vault is small enough that a Python-side
  // implementation would be more code for no real benefit.
  function computePageRank(nodes, links, damping = 0.85, iterations = 40) {
    const N = nodes.length;
    if (N === 0) return new Float64Array(0);
    const outDeg = new Float64Array(N);
    links.forEach((l) => { outDeg[l.source]++; });
    let ranks = new Float64Array(N).fill(1 / N);
    for (let iter = 0; iter < iterations; iter++) {
      const next = new Float64Array(N).fill((1 - damping) / N);
      links.forEach((l) => {
        const od = Math.max(1, outDeg[l.source]);
        next[l.target] += damping * (ranks[l.source] / od);
      });
      ranks = next;
    }
    return ranks;
  }

  // A real force-directed layout (repulsion + spring links + a gentle pull
  // toward each node's own cluster centroid, run to convergence once at
  // load time) rather than the reference's hand-placed demo clusters -
  // positions here come from the vault's actual link structure, not a
  // decorative scatter.
  function layoutForceDirected3D(nodes, links, clusterCount) {
    const N = nodes.length;
    if (N === 0) return;
    const rng = mulberry32(1337); // fixed seed - stable layout across reloads
    const pos = nodes.map(() => ({
      x: (rng() - 0.5) * 300, y: (rng() - 0.5) * 300, z: (rng() - 0.5) * 300,
    }));

    // Cluster centroids arranged around a ring so distinct types settle
    // into distinct "arms," echoing the reference's nebula-arm look.
    const centroids = [];
    for (let c = 0; c < clusterCount; c++) {
      const angle = (c / clusterCount) * Math.PI * 2;
      centroids.push({
        x: Math.cos(angle) * 260, y: Math.sin(angle) * 180,
        z: (rng() - 0.5) * 160,
      });
    }

    const ITER = 260;
    for (let iter = 0; iter < ITER; iter++) {
      const disp = pos.map(() => ({ x: 0, y: 0, z: 0 }));
      const cool = 1 - iter / ITER;

      // Repulsion between every pair - fine at this vault size (tens, not
      // thousands, of notes), no Barnes-Hut approximation needed.
      for (let i = 0; i < N; i++) {
        for (let j = i + 1; j < N; j++) {
          let dx = pos[i].x - pos[j].x, dy = pos[i].y - pos[j].y, dz = pos[i].z - pos[j].z;
          let d2 = dx * dx + dy * dy + dz * dz || 0.01;
          const force = 4200 / d2;
          const d = Math.sqrt(d2);
          dx /= d; dy /= d; dz /= d;
          disp[i].x += dx * force; disp[i].y += dy * force; disp[i].z += dz * force;
          disp[j].x -= dx * force; disp[j].y -= dy * force; disp[j].z -= dz * force;
        }
      }

      // Spring attraction along real edges toward an ideal rest length.
      links.forEach((l) => {
        const a = pos[l.source], b = pos[l.target];
        let dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
        const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.01;
        const rest = 90;
        const force = (d - rest) * 0.02;
        dx /= d; dy /= d; dz /= d;
        disp[l.source].x += dx * force; disp[l.source].y += dy * force; disp[l.source].z += dz * force;
        disp[l.target].x -= dx * force; disp[l.target].y -= dy * force; disp[l.target].z -= dz * force;
      });

      // Gentle pull toward this node's own cluster centroid.
      for (let i = 0; i < N; i++) {
        const c = centroids[nodes[i].cluster];
        disp[i].x += (c.x - pos[i].x) * 0.01;
        disp[i].y += (c.y - pos[i].y) * 0.01;
        disp[i].z += (c.z - pos[i].z) * 0.01;
      }

      for (let i = 0; i < N; i++) {
        pos[i].x += disp[i].x * cool * 0.06;
        pos[i].y += disp[i].y * cool * 0.06;
        pos[i].z += disp[i].z * cool * 0.06;
      }
    }

    nodes.forEach((n, i) => { n.x = pos[i].x; n.y = pos[i].y; n.z = pos[i].z; });
  }

  function mulberry32(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  async function fetchVaultGraph() {
    const res = await fetch("/api/graph");
    const raw = await res.json();

    const rawNodes = raw.nodes || [];
    const pathToIndex = new Map(rawNodes.map((n, i) => [n.path, i]));

    const nodes = rawNodes.map((n) => ({
      id: n.path,
      index: pathToIndex.get(n.path),
      title: n.title,
      cluster: clusterIndex(n.type),
      clusterName: CLUSTER_NAMES[n.type || ""] || "Vault",
      type: n.type || "",
      folder: n.folder || "(root)",
      tag: n.type ? `#${n.type}` : "#vault",
      inDegree: n.in || 0,
      outDegree: n.out || 0,
      mtime: n.mtime || null,
      isHub: false, // set below, once every node's real degree is known
    }));

    const links = (raw.edges || [])
      .map((e) => ({ source: pathToIndex.get(e.from), target: pathToIndex.get(e.to) }))
      .filter((l) => l.source !== undefined && l.target !== undefined);

    // Hub = real top-degree notes, not a fixed count - the top ~15% by
    // total degree, with a floor so a small vault doesn't call everything
    // a hub just because the bar is low.
    const degrees = nodes.map((n) => n.inDegree + n.outDegree).sort((a, b) => b - a);
    const hubCutoffIdx = Math.max(0, Math.floor(nodes.length * 0.15) - 1);
    const hubThreshold = Math.max(3, degrees[hubCutoffIdx] || 3);
    nodes.forEach((n) => { n.isHub = (n.inDegree + n.outDegree) >= hubThreshold; });

    const maxIn = Math.max(1, ...nodes.map((n) => n.inDegree));
    const maxOut = Math.max(1, ...nodes.map((n) => n.outDegree));
    nodes.forEach((n) => {
      n.normalizedIn = n.inDegree / maxIn;
      n.normalizedOut = n.outDegree / maxOut;
    });

    const ranks = computePageRank(nodes, links);
    let maxPR = 0;
    nodes.forEach((n, i) => { n.pageRank = ranks[i]; if (ranks[i] > maxPR) maxPR = ranks[i]; });
    nodes.forEach((n) => { n.normalizedPR = maxPR ? n.pageRank / maxPR : 0; });

    const now = Date.now() / 1000;
    nodes.forEach((n) => {
      n.lastEdited = n.mtime ? Math.max(0, (now - n.mtime) / 86400) : 9999; // days ago
    });

    layoutForceDirected3D(nodes, links, CLUSTER_ORDER.length);

    return { nodes, links, clusterNames: CLUSTER_NAMES, clusterOrder: CLUSTER_ORDER };
  }

  window.WickedBrainGraph3DData = { fetchVaultGraph };
})();
