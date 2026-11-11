/**
 * graph3d.js - Three.js WebGL "nebula" graph renderer.
 *
 * Adapted from a reference implementation the vault's owner built and
 * handed over (a recreation of Obsidian's Advanced Graph View / the
 * Graph Insight community plugin's Nebula theme) - the rendering
 * technique (additive glowing points via a custom shader, constellation
 * link lines, raycasted hover/click) is reused close to verbatim; only
 * the data it's fed is different - see graph3d-data.js, which computes
 * every metric here from this vault's real notes/links, never demo data.
 */
(function (window) {
  "use strict";

  function createGlowTexture() {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    const grad = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0.0, "rgba(255, 255, 255, 1.0)");
    grad.addColorStop(0.12, "rgba(255, 255, 255, 0.95)");
    grad.addColorStop(0.28, "rgba(230, 240, 255, 0.65)");
    grad.addColorStop(0.55, "rgba(180, 200, 255, 0.22)");
    grad.addColorStop(0.85, "rgba(140, 160, 255, 0.05)");
    grad.addColorStop(1.0, "rgba(0, 0, 0, 0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, 128, 128);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    return texture;
  }

  const COLOR_SCHEMES = {
    nebula: { name: "Nebula ✨", colors: ["#00e5ff", "#a855f7", "#f43f5e", "#f59e0b", "#818cf8", "#5fd4c4", "#9c9ac2"], hubColor: "#ffffff" },
    cyberpunk: { name: "Cyberpunk 🌆", colors: ["#00f0ff", "#ff003c", "#fcee0a", "#39ff14", "#b026ff", "#ff6ec7", "#7a7a7a"], hubColor: "#ffffff" },
    solar: { name: "Solar Flare ☀️", colors: ["#ffc107", "#ff5722", "#e91e63", "#ff8a80", "#ffeb3b", "#ff9e40", "#bdbdbd"], hubColor: "#ffffff" },
    cosmos: { name: "Deep Cosmos 🌌", colors: ["#38bdf8", "#818cf8", "#c084fc", "#2dd4bf", "#fb7185", "#60a5fa", "#94a3b8"], hubColor: "#ffffff" },
    emerald: { name: "Emerald Forest 🌲", colors: ["#10b981", "#34d399", "#06b6d4", "#84cc16", "#a7f3d0", "#22d3ee", "#a3a3a3"], hubColor: "#ffffff" },
  };

  class WickedBrainGraph3D {
    constructor(container, data) {
      this.container = container;
      this.data = data;
      this.nodes = data.nodes;
      this.links = data.links;

      this.settings = {
        sizeMetric: "inbound",
        colorMetric: "cluster",
        glowMetric: "outbound",
        colorScheme: "nebula",
        nodeSize: 0.7,
        showLinks: true,
        linkThickness: 1.4,
        linkOpacity: 0.12,
        is3D: true,
        autoOrbit: true,
        orbitSpeed: 0.35,
        searchQuery: "",
      };

      this.hoveredNode = null;
      this.selectedNode = null;
      this.raycaster = new THREE.Raycaster();
      this.raycaster.params.Points.threshold = 12;
      this.mouse = new THREE.Vector2(-9999, -9999);

      this.initThree();
      this.buildGraph();
      this.initStarfield();
      this.initEvents();
      this.animate();
    }

    initThree() {
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0x07070d);
      this.scene.fog = new THREE.FogExp2(0x07070d, 0.0009);

      const width = this.container.clientWidth;
      const height = this.container.clientHeight;

      this.camera = new THREE.PerspectiveCamera(50, width / height, 1, 10000);
      this.camera.position.set(120, 100, 620);

      this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true });
      this.renderer.setSize(width, height);
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.container.appendChild(this.renderer.domElement);

      this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
      this.controls.enableDamping = true;
      this.controls.dampingFactor = 0.05;
      this.controls.rotateSpeed = 0.6;
      this.controls.zoomSpeed = 0.8;
      this.controls.panSpeed = 0.6;
      this.controls.target.set(0, 0, 0);

      this.glowTexture = createGlowTexture();
    }

    buildGraph() {
      this.graphGroup = new THREE.Group();
      this.scene.add(this.graphGroup);

      const N = this.nodes.length;
      const positions = new Float32Array(N * 3);
      const colors = new Float32Array(N * 3);
      const sizes = new Float32Array(N);
      const alphas = new Float32Array(N);

      this.nodePositions = positions;
      this.nodeColors = colors;
      this.nodeSizes = sizes;
      this.nodeAlphas = alphas;

      for (let i = 0; i < N; i++) {
        const node = this.nodes[i];
        positions[i * 3] = node.x;
        positions[i * 3 + 1] = node.y;
        positions[i * 3 + 2] = node.z;
        const c = this.computeNodeColor(node);
        colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b;
        sizes[i] = this.computeNodeSize(node);
        alphas[i] = 1.0;
      }

      this.nodeGeometry = new THREE.BufferGeometry();
      this.nodeGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.nodeGeometry.setAttribute("customColor", new THREE.BufferAttribute(colors, 3));
      this.nodeGeometry.setAttribute("size", new THREE.BufferAttribute(sizes, 1));
      this.nodeGeometry.setAttribute("alpha", new THREE.BufferAttribute(alphas, 1));

      const nodeVertexShader = `
        attribute float size;
        attribute float alpha;
        attribute vec3 customColor;
        varying vec3 vColor;
        varying float vAlpha;
        uniform float globalSize;
        void main() {
          vColor = customColor;
          vAlpha = alpha;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * globalSize * (600.0 / -mvPosition.z);
          gl_Position = projectionMatrix * mvPosition;
        }
      `;
      const nodeFragmentShader = `
        uniform sampler2D pointTexture;
        varying vec3 vColor;
        varying float vAlpha;
        void main() {
          vec4 texColor = texture2D(pointTexture, gl_PointCoord);
          if (texColor.a < 0.01) discard;
          vec3 finalColor = mix(vColor, vec3(1.0), texColor.r * 0.45);
          gl_FragColor = vec4(finalColor, texColor.a * vAlpha);
        }
      `;

      this.nodeMaterial = new THREE.ShaderMaterial({
        uniforms: { pointTexture: { value: this.glowTexture }, globalSize: { value: this.settings.nodeSize * 22.0 } },
        vertexShader: nodeVertexShader, fragmentShader: nodeFragmentShader,
        blending: THREE.AdditiveBlending, depthWrite: false, transparent: true,
      });

      this.pointsMesh = new THREE.Points(this.nodeGeometry, this.nodeMaterial);
      this.graphGroup.add(this.pointsMesh);

      const L = this.links.length;
      const linkPositions = new Float32Array(L * 6);
      const linkColors = new Float32Array(L * 6);
      this.linkPositions = linkPositions;
      this.linkColors = linkColors;

      for (let i = 0; i < L; i++) {
        const link = this.links[i];
        const src = this.nodes[link.source];
        const tgt = this.nodes[link.target];
        linkPositions[i * 6] = src.x; linkPositions[i * 6 + 1] = src.y; linkPositions[i * 6 + 2] = src.z;
        linkPositions[i * 6 + 3] = tgt.x; linkPositions[i * 6 + 4] = tgt.y; linkPositions[i * 6 + 5] = tgt.z;
        const srcCol = this.computeNodeColor(src);
        const tgtCol = this.computeNodeColor(tgt);
        linkColors[i * 6] = srcCol.r; linkColors[i * 6 + 1] = srcCol.g; linkColors[i * 6 + 2] = srcCol.b;
        linkColors[i * 6 + 3] = tgtCol.r; linkColors[i * 6 + 4] = tgtCol.g; linkColors[i * 6 + 5] = tgtCol.b;
      }

      this.linkGeometry = new THREE.BufferGeometry();
      this.linkGeometry.setAttribute("position", new THREE.BufferAttribute(linkPositions, 3));
      this.linkGeometry.setAttribute("color", new THREE.BufferAttribute(linkColors, 3));

      this.linkMaterial = new THREE.LineBasicMaterial({
        vertexColors: true, transparent: true, opacity: this.settings.linkOpacity,
        blending: THREE.AdditiveBlending, depthWrite: false, linewidth: this.settings.linkThickness,
      });
      this.linesMesh = new THREE.LineSegments(this.linkGeometry, this.linkMaterial);
      this.graphGroup.add(this.linesMesh);

      const ringGeo = new THREE.RingGeometry(1.2, 1.8, 32);
      const ringMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide, transparent: true, opacity: 0.0, blending: THREE.AdditiveBlending });
      this.highlightRing = new THREE.Mesh(ringGeo, ringMat);
      this.highlightRing.visible = false;
      this.scene.add(this.highlightRing);

      this.hoverLinksGeo = new THREE.BufferGeometry();
      this.hoverLinksMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false, linewidth: 2.0 });
      this.hoverLinesMesh = new THREE.LineSegments(this.hoverLinksGeo, this.hoverLinksMat);
      this.hoverLinesMesh.visible = false;
      this.graphGroup.add(this.hoverLinesMesh);
    }

    initStarfield() {
      const dustCount = 900;
      const dustGeo = new THREE.BufferGeometry();
      const dustPos = new Float32Array(dustCount * 3);
      const dustCol = new Float32Array(dustCount * 3);
      for (let i = 0; i < dustCount; i++) {
        dustPos[i * 3] = (Math.random() - 0.5) * 3000;
        dustPos[i * 3 + 1] = (Math.random() - 0.5) * 2600;
        dustPos[i * 3 + 2] = (Math.random() - 0.5) * 2600;
        const shade = 0.2 + Math.random() * 0.4;
        dustCol[i * 3] = shade * 0.7; dustCol[i * 3 + 1] = shade * 0.8; dustCol[i * 3 + 2] = shade;
      }
      dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
      dustGeo.setAttribute("color", new THREE.BufferAttribute(dustCol, 3));
      const dustMat = new THREE.PointsMaterial({ size: 2.0, vertexColors: true, transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false });
      this.starfield = new THREE.Points(dustGeo, dustMat);
      this.scene.add(this.starfield);
    }

    computeNodeColor(node) {
      const scheme = COLOR_SCHEMES[this.settings.colorScheme] || COLOR_SCHEMES.nebula;
      if (node.isHub && this.settings.colorMetric === "cluster") return new THREE.Color(scheme.hubColor);
      switch (this.settings.colorMetric) {
        case "cluster":
          return new THREE.Color(scheme.colors[node.cluster % scheme.colors.length]);
        case "inbound": {
          const t = Math.min(1.0, node.normalizedIn * 1.5);
          return new THREE.Color().setHSL(0.6 - t * 0.5, 0.9, 0.4 + t * 0.5);
        }
        case "outbound": {
          const t = Math.min(1.0, node.normalizedOut * 1.5);
          return new THREE.Color().setHSL(0.9 - t * 0.3, 0.9, 0.4 + t * 0.5);
        }
        case "recency": {
          const t = 1.0 - Math.min(1.0, node.lastEdited / 30);
          return new THREE.Color().setHSL(0.75 - t * 0.65, 0.85, 0.4 + t * 0.4);
        }
        default:
          return new THREE.Color(scheme.colors[0]);
      }
    }

    computeNodeSize(node) {
      let metricVal = 1.0;
      switch (this.settings.sizeMetric) {
        case "inbound": metricVal = 0.9 + Math.pow(node.normalizedIn, 0.65) * 5.5; break;
        case "outbound": metricVal = 0.9 + Math.pow(node.normalizedOut, 0.65) * 5.0; break;
        case "pagerank": metricVal = 1.0 + Math.pow(node.normalizedPR, 0.5) * 6.0; break;
        case "recency": metricVal = 1.0 + (1.0 - Math.min(1.0, node.lastEdited / 30)) * 4.0; break;
        case "uniform": default: metricVal = 1.6; break;
      }
      if (node.isHub) metricVal *= 1.4;
      return metricVal;
    }

    updateAppearance() {
      const N = this.nodes.length;
      const colors = this.nodeColors;
      const sizes = this.nodeSizes;
      for (let i = 0; i < N; i++) {
        const node = this.nodes[i];
        const c = this.computeNodeColor(node);
        colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b;
        sizes[i] = this.computeNodeSize(node);
      }
      this.nodeGeometry.attributes.customColor.needsUpdate = true;
      this.nodeGeometry.attributes.size.needsUpdate = true;
      this.nodeMaterial.uniforms.globalSize.value = this.settings.nodeSize * 22.0;

      this.linesMesh.visible = this.settings.showLinks;
      this.linkMaterial.opacity = this.settings.linkOpacity;
      this.linkMaterial.linewidth = this.settings.linkThickness;

      const L = this.links.length;
      const linkCols = this.linkColors;
      for (let i = 0; i < L; i++) {
        const link = this.links[i];
        const srcCol = this.computeNodeColor(this.nodes[link.source]);
        const tgtCol = this.computeNodeColor(this.nodes[link.target]);
        linkCols[i * 6] = srcCol.r; linkCols[i * 6 + 1] = srcCol.g; linkCols[i * 6 + 2] = srcCol.b;
        linkCols[i * 6 + 3] = tgtCol.r; linkCols[i * 6 + 4] = tgtCol.g; linkCols[i * 6 + 5] = tgtCol.b;
      }
      this.linkGeometry.attributes.color.needsUpdate = true;
    }

    applySearchFilter(query) {
      this.settings.searchQuery = query.toLowerCase().trim();
      const q = this.settings.searchQuery;
      const N = this.nodes.length;
      const alphas = this.nodeAlphas;

      if (!q) {
        for (let i = 0; i < N; i++) alphas[i] = 1.0;
        this.nodeGeometry.attributes.alpha.needsUpdate = true;
        this.linkMaterial.opacity = this.settings.linkOpacity;
        return;
      }

      for (let i = 0; i < N; i++) {
        const node = this.nodes[i];
        let matches;
        if (q.startsWith("tag:")) matches = node.tag.toLowerCase().includes(q.replace("tag:", "").trim());
        else if (q.startsWith("path:") || q.startsWith("folder:")) matches = node.folder.toLowerCase().includes(q.replace(/(path|folder):/, "").trim());
        else if (q.startsWith("cluster:")) matches = node.clusterName.toLowerCase().includes(q.replace("cluster:", "").trim());
        else matches = node.title.toLowerCase().includes(q) || node.tag.toLowerCase().includes(q);
        alphas[i] = matches ? 1.0 : 0.06;
      }
      this.nodeGeometry.attributes.alpha.needsUpdate = true;
      this.linkMaterial.opacity = this.settings.linkOpacity * 0.35;
    }

    set2DMode(is2D) {
      this.settings.is3D = !is2D;
      if (is2D) {
        this.settings.autoOrbit = false;
        const currentDistance = this.camera.position.length();
        new TWEEN.Tween(this.camera.position).to({ x: 0, y: 0, z: Math.max(500, currentDistance) }, 800).easing(TWEEN.Easing.Cubic.Out).start();
        new TWEEN.Tween(this.camera.up).to({ x: 0, y: 1, z: 0 }, 800).start();
        this.controls.enableRotate = false;
      } else {
        this.controls.enableRotate = true;
        new TWEEN.Tween(this.camera.position).to({ x: 120, y: 100, z: 620 }, 800).easing(TWEEN.Easing.Cubic.Out).start();
      }
    }

    resetCamera() {
      new TWEEN.Tween(this.camera.position).to({ x: 120, y: 100, z: 620 }, 900).easing(TWEEN.Easing.Cubic.Out).start();
      new TWEEN.Tween(this.controls.target).to({ x: 0, y: 0, z: 0 }, 900).easing(TWEEN.Easing.Cubic.Out).start();
    }

    focusNode(node) {
      this.selectedNode = node;
      const targetPos = new THREE.Vector3(node.x, node.y, node.z);
      const camOffset = new THREE.Vector3(70, 50, 150);
      const targetCamPos = targetPos.clone().add(camOffset);

      new TWEEN.Tween(this.controls.target).to(targetPos, 800).easing(TWEEN.Easing.Cubic.Out).start();
      new TWEEN.Tween(this.camera.position).to(targetCamPos, 800).easing(TWEEN.Easing.Cubic.Out).start();

      this.highlightRing.position.copy(targetPos);
      this.highlightRing.scale.set(this.computeNodeSize(node) * 8.0, this.computeNodeSize(node) * 8.0, 1);
      this.highlightRing.quaternion.copy(this.camera.quaternion);
      this.highlightRing.visible = true;
      this.highlightRing.material.opacity = 0.85;

      if (window.WickedBrainGraph3DUI && window.WickedBrainGraph3DUI.openInspector) {
        window.WickedBrainGraph3DUI.openInspector(node);
      }
    }

    initEvents() {
      const el = this.renderer.domElement;
      el.addEventListener("mousemove", (e) => {
        const rect = el.getBoundingClientRect();
        this.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
        this.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
        this.checkHover(e.clientX, e.clientY);
      });
      el.addEventListener("click", () => { if (this.hoveredNode) this.focusNode(this.hoveredNode); });
      window.addEventListener("resize", () => this.handleResize());
    }

    handleResize() {
      const w = this.container.clientWidth;
      const h = this.container.clientHeight;
      if (!w || !h) return;
      this.camera.aspect = w / h;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(w, h);
    }

    checkHover(screenX, screenY) {
      this.raycaster.setFromCamera(this.mouse, this.camera);
      const intersects = this.raycaster.intersectObject(this.pointsMesh);
      if (intersects.length > 0) {
        const node = this.nodes[intersects[0].index];
        this.hoveredNode = node;
        this.container.style.cursor = "pointer";

        const connected = this.links.filter((l) => l.source === node.index || l.target === node.index);
        if (connected.length > 0) {
          const posArr = new Float32Array(connected.length * 6);
          connected.forEach((l, i) => {
            const s = this.nodes[l.source], t = this.nodes[l.target];
            posArr[i * 6] = s.x; posArr[i * 6 + 1] = s.y; posArr[i * 6 + 2] = s.z;
            posArr[i * 6 + 3] = t.x; posArr[i * 6 + 4] = t.y; posArr[i * 6 + 5] = t.z;
          });
          this.hoverLinksGeo.setAttribute("position", new THREE.BufferAttribute(posArr, 3));
          this.hoverLinksMat.color = this.computeNodeColor(node);
          this.hoverLinesMesh.visible = true;
        }
        if (window.WickedBrainGraph3DUI && window.WickedBrainGraph3DUI.showTooltip) window.WickedBrainGraph3DUI.showTooltip(node, screenX, screenY);
      } else {
        this.hoveredNode = null;
        this.hoverLinesMesh.visible = false;
        this.container.style.cursor = "default";
        if (window.WickedBrainGraph3DUI && window.WickedBrainGraph3DUI.hideTooltip) window.WickedBrainGraph3DUI.hideTooltip();
      }
    }

    animate() {
      this._raf = requestAnimationFrame(() => this.animate());
      if (window.TWEEN) TWEEN.update();
      if (this.settings.autoOrbit && this.settings.is3D && !this.selectedNode) {
        this.graphGroup.rotation.y += 0.0006 * this.settings.orbitSpeed;
        if (this.starfield) this.starfield.rotation.y += 0.0002;
      }
      if (this.highlightRing.visible) this.highlightRing.quaternion.copy(this.camera.quaternion);
      this.controls.update();
      this.renderer.render(this.scene, this.camera);
    }

    dispose() {
      if (this._raf) cancelAnimationFrame(this._raf);
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode) this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
    }

    captureScreenshot() {
      this.renderer.render(this.scene, this.camera);
      return this.renderer.domElement.toDataURL("image/png");
    }
  }

  window.WickedBrainGraph3D = WickedBrainGraph3D;
  window.WickedBrainGraph3DColorSchemes = COLOR_SCHEMES;
})(window);
