/**
 * graph3d-ui.js - sidebar controls, tooltip, and note inspector for the
 * nebula graph. Adapted from the reference implementation; every stat
 * shown here is real (inbound/outbound/PageRank/recency computed in
 * graph3d-data.js from actual vault links) - the reference's "opened N
 * times" stat is dropped entirely rather than faked, since this vault has
 * no such tracking.
 */
(function (window) {
  "use strict";

  class WickedBrainGraph3DUI {
    constructor(graphView, container) {
      this.graphView = graphView;
      this.root = container;
      this.tooltip = this.root.querySelector("#graph3d-tooltip");
      this.inspector = this.root.querySelector("#g3d-inspector");
      this.initElements();
      this.bindControls();
      this.bindPresets();
      this.bindFilter();
      this.bindInspector();
      this.renderClusterLegend();
      this.updateStatusCounts();
    }

    $(sel) { return this.root.querySelector(sel); }

    initElements() {
      this.selectSize = this.$("#g3d-select-size");
      this.selectColor = this.$("#g3d-select-color");
      this.selectGlow = this.$("#g3d-select-glow");
      this.selectScheme = this.$("#g3d-select-scheme");

      this.sliderNodeSize = this.$("#g3d-slider-node-size");
      this.valNodeSize = this.$("#g3d-val-node-size");

      this.checkShowLinks = this.$("#g3d-check-show-links");
      this.sliderLinkThickness = this.$("#g3d-slider-link-thickness");
      this.valLinkThickness = this.$("#g3d-val-link-thickness");
      this.sliderLinkOpacity = this.$("#g3d-slider-link-opacity");
      this.valLinkOpacity = this.$("#g3d-val-link-opacity");

      this.check3D = this.$("#g3d-check-3d");
      this.checkOrbit = this.$("#g3d-check-orbit");

      this.sidebar = this.$("#g3d-panel");
      this.panelToggleBtn = this.$("#g3d-panel-toggle-btn");
      this.btnMinimize = this.$("#g3d-btn-minimize");

      this.filterInput = this.$("#g3d-filter-input");

      this.statNodes = this.$("#g3d-stat-nodes");
      this.statLinks = this.$("#g3d-stat-links");
      this.btnExportPng = this.$("#g3d-btn-export-png");
      this.btnResetView = this.$("#g3d-btn-reset-view");
      this.btnToggle3D = this.$("#g3d-btn-toggle-3d");
    }

    bindControls() {
      this.root.querySelectorAll(".g3d-section-title").forEach((title) => {
        title.addEventListener("click", () => title.parentElement.classList.toggle("g3d-closed"));
      });

      if (this.btnMinimize) {
        this.btnMinimize.addEventListener("click", () => {
          this.sidebar.classList.add("g3d-collapsed");
          if (this.panelToggleBtn) this.panelToggleBtn.style.display = "flex";
        });
      }
      if (this.panelToggleBtn) {
        this.panelToggleBtn.addEventListener("click", () => {
          this.sidebar.classList.remove("g3d-collapsed");
          this.panelToggleBtn.style.display = "none";
        });
      }

      this.selectSize.addEventListener("change", (e) => { this.graphView.settings.sizeMetric = e.target.value; this.graphView.updateAppearance(); });
      this.selectColor.addEventListener("change", (e) => { this.graphView.settings.colorMetric = e.target.value; this.graphView.updateAppearance(); });
      this.selectGlow.addEventListener("change", (e) => { this.graphView.settings.glowMetric = e.target.value; this.graphView.updateAppearance(); });
      this.selectScheme.addEventListener("change", (e) => { this.graphView.settings.colorScheme = e.target.value; this.graphView.updateAppearance(); this.renderClusterLegend(); });

      this.sliderNodeSize.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        this.valNodeSize.textContent = val.toFixed(3);
        this.graphView.settings.nodeSize = val;
        this.graphView.updateAppearance();
      });

      this.checkShowLinks.addEventListener("change", (e) => { this.graphView.settings.showLinks = e.target.checked; this.graphView.updateAppearance(); });
      this.sliderLinkThickness.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        this.valLinkThickness.textContent = val.toFixed(3);
        this.graphView.settings.linkThickness = val;
        this.graphView.updateAppearance();
      });
      this.sliderLinkOpacity.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        this.valLinkOpacity.textContent = val.toFixed(3);
        this.graphView.settings.linkOpacity = val;
        this.graphView.updateAppearance();
      });

      this.check3D.addEventListener("change", (e) => {
        this.graphView.set2DMode(!e.target.checked);
        if (this.btnToggle3D) this.btnToggle3D.textContent = e.target.checked ? "3D" : "2D";
      });
      this.checkOrbit.addEventListener("change", (e) => { this.graphView.settings.autoOrbit = e.target.checked; });

      if (this.btnResetView) this.btnResetView.addEventListener("click", () => this.graphView.resetCamera());
      if (this.btnToggle3D) {
        this.btnToggle3D.addEventListener("click", () => {
          const is3D = !this.graphView.settings.is3D;
          this.check3D.checked = is3D;
          this.graphView.set2DMode(!is3D);
          this.btnToggle3D.textContent = is3D ? "3D" : "2D";
        });
      }
      if (this.btnExportPng) {
        this.btnExportPng.addEventListener("click", () => {
          const dataUrl = this.graphView.captureScreenshot();
          const a = document.createElement("a");
          a.download = "brain_vault_graph.png";
          a.href = dataUrl;
          a.click();
        });
      }
    }

    bindPresets() {
      const presetSelect = this.$("#g3d-select-preset");
      if (!presetSelect) return;
      const presets = {
        default: { sizeMetric: "inbound", colorMetric: "cluster", glowMetric: "outbound", colorScheme: "nebula", nodeSize: 0.7, showLinks: true, linkThickness: 1.4, linkOpacity: 0.12, is3D: true },
        hubs: { sizeMetric: "pagerank", colorMetric: "inbound", glowMetric: "pagerank", colorScheme: "nebula", nodeSize: 0.9, showLinks: true, linkThickness: 1.8, linkOpacity: 0.16, is3D: true },
        recency: { sizeMetric: "recency", colorMetric: "recency", glowMetric: "inbound", colorScheme: "solar", nodeSize: 0.8, showLinks: true, linkThickness: 1.2, linkOpacity: 0.10, is3D: true },
        cyberpunk: { sizeMetric: "inbound", colorMetric: "cluster", glowMetric: "outbound", colorScheme: "cyberpunk", nodeSize: 0.75, showLinks: true, linkThickness: 1.6, linkOpacity: 0.14, is3D: true },
        flat2d: { sizeMetric: "inbound", colorMetric: "cluster", glowMetric: "outbound", colorScheme: "cosmos", nodeSize: 0.65, showLinks: true, linkThickness: 1.3, linkOpacity: 0.12, is3D: false },
      };
      presetSelect.addEventListener("change", (e) => {
        const p = presets[e.target.value];
        if (!p) return;
        this.selectSize.value = p.sizeMetric;
        this.selectColor.value = p.colorMetric;
        this.selectGlow.value = p.glowMetric;
        this.selectScheme.value = p.colorScheme;
        this.sliderNodeSize.value = p.nodeSize; this.valNodeSize.textContent = p.nodeSize.toFixed(3);
        this.checkShowLinks.checked = p.showLinks;
        this.sliderLinkThickness.value = p.linkThickness; this.valLinkThickness.textContent = p.linkThickness.toFixed(3);
        this.sliderLinkOpacity.value = p.linkOpacity; this.valLinkOpacity.textContent = p.linkOpacity.toFixed(3);
        this.check3D.checked = p.is3D;
        Object.assign(this.graphView.settings, p);
        this.graphView.set2DMode(!p.is3D);
        this.graphView.updateAppearance();
        this.renderClusterLegend();
      });
    }

    bindFilter() {
      if (!this.filterInput) return;
      this.filterInput.addEventListener("input", (e) => this.graphView.applySearchFilter(e.target.value));
    }

    renderClusterLegend() {
      const el = this.$("#g3d-cluster-legend");
      if (!el) return;
      const scheme = window.WickedBrainGraph3DColorSchemes[this.graphView.settings.colorScheme] || window.WickedBrainGraph3DColorSchemes.nebula;
      const order = this.graphView.data.clusterOrder;
      const names = this.graphView.data.clusterNames;
      el.innerHTML = order
        .map((type, i) => {
          const count = this.graphView.nodes.filter((n) => n.cluster === i).length;
          if (!count) return "";
          const color = scheme.colors[i % scheme.colors.length];
          return `<div class="g3d-cluster-legend-row"><span class="g3d-cluster-swatch" style="background:${color}"></span>${names[type] || type} (${count})</div>`;
        })
        .join("");
    }

    showTooltip(node, screenX, screenY) {
      if (!this.tooltip) return;
      const rect = this.root.getBoundingClientRect();
      this.$("#g3d-tooltip-title").textContent = node.title;
      const badge = this.$("#g3d-tooltip-badge");
      badge.textContent = node.clusterName;
      const scheme = window.WickedBrainGraph3DColorSchemes[this.graphView.settings.colorScheme] || window.WickedBrainGraph3DColorSchemes.nebula;
      const color = node.isHub ? scheme.hubColor : scheme.colors[node.cluster % scheme.colors.length];
      badge.style.backgroundColor = color + "33";
      badge.style.color = color;
      badge.style.border = `1px solid ${color}66`;

      this.$("#g3d-tooltip-in").textContent = node.inDegree;
      this.$("#g3d-tooltip-out").textContent = node.outDegree;
      this.$("#g3d-tooltip-pr").textContent = (node.pageRank * 1000).toFixed(2);

      this.tooltip.style.left = `${screenX - rect.left}px`;
      this.tooltip.style.top = `${screenY - rect.top}px`;
      this.tooltip.classList.add("g3d-visible");
    }

    hideTooltip() { if (this.tooltip) this.tooltip.classList.remove("g3d-visible"); }

    bindInspector() {
      const closeBtn = this.$("#g3d-btn-close-inspector");
      if (closeBtn) closeBtn.addEventListener("click", () => this.closeInspector());
      const openBtn = this.$("#g3d-btn-open-note");
      if (openBtn) {
        openBtn.addEventListener("click", () => {
          if (this._inspectedPath && window.WickedBrainOpenNote) window.WickedBrainOpenNote(this._inspectedPath);
        });
      }
    }

    openInspector(node) {
      if (!this.inspector) return;
      this._inspectedPath = node.id;

      this.$("#g3d-inspector-title").textContent = node.title;
      this.$("#g3d-inspector-cluster-tag").textContent = node.clusterName;
      this.$("#g3d-inspector-folder").textContent = node.folder;
      this.$("#g3d-inspector-tag").textContent = node.tag;

      this.$("#g3d-inspector-in").textContent = node.inDegree;
      this.$("#g3d-inspector-out").textContent = node.outDegree;
      this.$("#g3d-inspector-pr").textContent = (node.pageRank * 1000).toFixed(2);
      this.$("#g3d-inspector-recency").textContent =
        node.lastEdited >= 9999 ? "unknown" : node.lastEdited < 1 ? "today" : `${Math.round(node.lastEdited)}d ago`;

      const backlinkList = this.$("#g3d-inspector-backlinks");
      backlinkList.innerHTML = "";
      const connectedLinks = this.graphView.links.filter((l) => l.target === node.index || l.source === node.index).slice(0, 12);
      connectedLinks.forEach((l) => {
        const otherIdx = l.target === node.index ? l.source : l.target;
        const otherNode = this.graphView.nodes[otherIdx];
        const isBacklink = l.target === node.index;
        const item = document.createElement("div");
        item.className = "g3d-link-pill-item";
        item.innerHTML = `<span>${isBacklink ? "← " : "→ "}${escapeHtml(otherNode.title)}</span><span style="color:var(--g3d-text-faint);font-size:9px">${escapeHtml(otherNode.tag)}</span>`;
        item.addEventListener("click", () => this.graphView.focusNode(otherNode));
        backlinkList.appendChild(item);
      });

      this.inspector.classList.add("g3d-open");
    }

    closeInspector() {
      if (this.inspector) this.inspector.classList.remove("g3d-open");
      if (this.graphView.highlightRing) this.graphView.highlightRing.visible = false;
      this.graphView.selectedNode = null;
    }

    updateStatusCounts() {
      if (this.statNodes) this.statNodes.textContent = this.graphView.nodes.length.toLocaleString();
      if (this.statLinks) this.statLinks.textContent = this.graphView.links.length.toLocaleString();
    }
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  window.WickedBrainGraph3DUIClass = WickedBrainGraph3DUI;
})(window);
