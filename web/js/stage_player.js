/**
 * 2D Auto-Run Looping Stage Player (`stage_player.js`)
 * Supports In-Place & Forward Auto-Run Looping, Crisp Pixel Art (`imageSmoothingEnabled = false`),
 * Integer Zoom (`1x, 2x, 3x, 4x`), Head Anchor & Baseline Guides, and Keyboard Controls.
 */
class StagePlayer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext("2d");
    this.atlasImg = new Image();
    this.bgImg = null;
    this.manifest = null;
    this.analysis = null;

    this.currentState = "walk";
    this.statesMap = {};
    this.frameIdx = 0;
    this.lastFrameTs = 0;
    this.fpsOverride = null;

    this.forwardMode = true;
    this.pixelMode = false;
    this.zoom = 1;
    this.showGuides = true;

    this.scrollX = 0;
    this.actorY = 0;
    this.vy = 0;
    this.facing = 1;
    this.keys = {};

    this._bindKeyboard();
    requestAnimationFrame(ts => this._loop(ts));
  }

  _bindKeyboard() {
    window.addEventListener("keydown", e => {
      if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;
      this.keys[e.code] = true;
      if (e.code === "Space" && this.actorY === 0) {
        e.preventDefault();
        this.vy = -9.5;
      }
    });
    window.addEventListener("keyup", e => {
      this.keys[e.code] = false;
    });
  }

  loadRun(atlasUrl, manifest, analysis) {
    this.manifest = manifest;
    this.analysis = analysis;
    this.statesMap = {};

    const rows = manifest?.animation?.rows || {};
    const layoutRows = manifest?.frame_layout?.rows || {};
    const layoutFrames = manifest?.frame_layout?.frames || [];
    const cellW = manifest?.cell?.width || manifest?.frame_layout?.cellWidth || 256;
    const cellH = manifest?.cell?.height || manifest?.frame_layout?.cellHeight || 256;

    Object.keys(rows).forEach((st, rowIdx) => {
      const rFrames = layoutRows[st] || [];
      this.statesMap[st] = {
        fps: rows[st].fps || 8,
        loop: rows[st].loop !== false,
        frames: rFrames.map((rf, i) => ({
          x: rf.x !== undefined ? rf.x : i * cellW,
          y: rf.y !== undefined ? rf.y : rowIdx * cellH,
          w: rf.w || rf.width || cellW,
          h: rf.h || rf.height || cellH,
        })),
      };
    });

    layoutFrames.forEach(lf => {
      const st = lf.state;
      if (!this.statesMap[st]) {
        this.statesMap[st] = { fps: 8, loop: true, frames: [] };
      }
      this.statesMap[st].frames.push({
        x: lf.x,
        y: lf.y,
        w: lf.w || lf.width || cellW,
        h: lf.h || lf.height || cellH,
      });
    });

    const avail = Object.keys(this.statesMap);
    if (!avail.includes(this.currentState)) {
      this.currentState = avail.includes("walk") ? "walk" : (avail[0] || "idle");
    }
    this.frameIdx = 0;
    this.atlasImg.src = atlasUrl;
  }

  setState(stateName) {
    if (this.statesMap[stateName]) {
      this.currentState = stateName;
      this.frameIdx = 0;
      this.fpsOverride = null;
    }
  }

  setCustomBackgroundUrl(url) {
    const img = new Image();
    img.onload = () => { this.bgImg = img; };
    img.src = url;
  }

  setCustomBackground(file) {
    const reader = new FileReader();
    reader.onload = e => {
      const img = new Image();
      img.onload = () => { this.bgImg = img; };
      img.src = e.target.result;
    };
    reader.readAsDataURL(file);
  }

  _loop(ts) {
    const st = this.statesMap[this.currentState];
    const fps = this.fpsOverride || st?.fps || 8;
    const interval = 1000 / Math.max(1, fps);

    if (st && st.frames.length > 0 && ts - this.lastFrameTs >= interval) {
      this.frameIdx = (this.frameIdx + 1) % st.frames.length;
      this.lastFrameTs = ts;
    }

    // Movement & Jump physics
    if (this.keys["ArrowRight"] || this.keys["KeyD"]) {
      this.facing = 1;
      this.scrollX += 3.2;
    } else if (this.keys["ArrowLeft"] || this.keys["KeyA"]) {
      this.facing = -1;
      this.scrollX -= 3.2;
    } else if (this.forwardMode) {
      this.scrollX += 2.4;
    }

    if (this.actorY < 0 || this.vy < 0) {
      this.actorY += this.vy;
      this.vy += 0.52;
      if (this.actorY >= 0) {
        this.actorY = 0;
        this.vy = 0;
      }
    }

    this._render(st);
    requestAnimationFrame(nextTs => this._loop(nextTs));
  }

  _render(st) {
    const { ctx, canvas } = this;
    const W = canvas.width;
    const H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.imageSmoothingEnabled = !this.pixelMode;

    const groundY = H - 46;

    // 1. Optional scrolling background tile
    if (this.bgImg && this.bgImg.complete) {
      const bw = this.bgImg.width * (H / Math.max(1, this.bgImg.height));
      const off = ((this.scrollX * 0.6) % bw + bw) % bw;
      for (let x = -off; x < W; x += bw) {
        ctx.globalAlpha = 0.45;
        ctx.drawImage(this.bgImg, x, 0, bw, H);
        ctx.globalAlpha = 1.0;
      }
    }

    // 2. Procedural stage floor & scrolling 64px ruler ticks
    ctx.strokeStyle = "#4b5563";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(0, groundY);
    ctx.lineTo(W, groundY);
    ctx.stroke();

    const tickStep = 64;
    const tickOffset = ((this.scrollX % tickStep) + tickStep) % tickStep;
    ctx.fillStyle = "#6b7280";
    ctx.font = "10px monospace";
    for (let x = -tickOffset; x < W; x += tickStep) {
      ctx.beginPath();
      ctx.moveTo(x, groundY);
      ctx.lineTo(x, groundY + 9);
      ctx.stroke();
    }

    // 3. Draw Character Sprite & Guides
    if (st && st.frames.length > 0 && this.atlasImg.complete && this.atlasImg.naturalWidth > 0) {
      const f = st.frames[this.frameIdx % st.frames.length];
      // Auto-scale large HD cells (e.g. 256px) nicely onto the 330px stage at 1x zoom
      const baseScale = f.h > 210 ? 200 / f.h : 1.0;
      const scale = this.pixelMode ? this.zoom : baseScale * this.zoom;
      const drawW = Math.round(f.w * scale);
      const drawH = Math.round(f.h * scale);

      const cx = Math.round(W / 2);
      const topY = Math.round(groundY - drawH + this.actorY);

      // Projected Dynamic Shadow under feet
      ctx.fillStyle = "rgba(8, 8, 16, 0.5)";
      ctx.beginPath();
      ctx.ellipse(
        cx,
        groundY - 2,
        Math.max(18, drawW * 0.22),
        Math.max(4, drawH * 0.038),
        0,
        0,
        Math.PI * 2
      );
      ctx.fill();

      ctx.save();
      ctx.translate(cx, topY);
      ctx.scale(this.facing, 1);
      ctx.drawImage(this.atlasImg, f.x, f.y, f.w, f.h, -drawW / 2, 0, drawW, drawH);
      ctx.restore();

      // 4. Head Anchor & Baseline Measurement Guides
      if (this.showGuides) {
        const stateAnalysis = this.analysis?.states?.[this.currentState];
        const framesInfo = stateAnalysis?.frames || [];
        const refFrame = framesInfo[0];
        const curFrame = framesInfo[this.frameIdx % Math.max(1, framesInfo.length)];

        if (refFrame && curFrame) {
          const refScreenX = cx - drawW / 2 + (refFrame.head_x / f.w) * drawW;
          const curScreenX = cx - drawW / 2 + (curFrame.head_x / f.w) * drawW;

          // Reference Head Lock Line (Green dashed)
          ctx.save();
          ctx.setLineDash([4, 4]);
          ctx.strokeStyle = "rgba(16, 185, 129, 0.75)";
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(refScreenX, topY + 6);
          ctx.lineTo(refScreenX, groundY);
          ctx.stroke();

          // Current Frame Head Line (Pink if drifted)
          if (Math.abs(curFrame.head_dx_px) > 1.0) {
            ctx.strokeStyle = "rgba(239, 68, 68, 0.9)";
            ctx.beginPath();
            ctx.moveTo(curScreenX, topY + 6);
            ctx.lineTo(curScreenX, topY + drawH * 0.45);
            ctx.stroke();
          }
          ctx.restore();
        }

        // HUD overlay top-left of canvas
        ctx.fillStyle = "rgba(13, 17, 23, 0.85)";
        ctx.fillRect(10, 10, 245, 46);
        ctx.strokeStyle = "rgba(48, 54, 61, 0.8)";
        ctx.lineWidth = 1;
        ctx.strokeRect(10, 10, 245, 46);

        ctx.fillStyle = "#58a6ff";
        ctx.font = "600 11.5px 'Be Vietnam Pro', 'Inter', sans-serif";
        ctx.fillText(
          `State: ${this.currentState}  |  Frame: ${this.frameIdx + 1}/${st.frames.length}`,
          18,
          27
        );
        ctx.fillStyle = "#8b949e";
        ctx.font = "11px 'JetBrains Mono', monospace";
        ctx.fillText(
          `Cell: ${f.w}x${f.h}px  |  ${this.forwardMode ? "Forward Loop" : "In-Place"}`,
          18,
          45
        );
      }
    }
  }
}

window.StagePlayer = StagePlayer;
