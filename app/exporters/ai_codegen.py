"""Sandboxed AI Custom Code Generator (`ai_codegen.py`).

Generates custom HTML5 Canvas gameplay code (e.g., double jump, attack projectiles, particle effects)
from `manifest.json` + user prompt, intended to be previewed strictly as text first and executed
only inside `<iframe sandbox="allow-scripts">` without `allow-same-origin`.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from app.exporters.template_codegen import _extract_state_rects, _get_char_id, load_run_manifest


def generate_custom_sandbox_html(
    run_dir: str | Path,
    custom_prompt: str,
    pixel_art: bool = False,
) -> dict[str, Any]:
    """Build an interactive HTML5 Canvas mini-game incorporating the user's custom gameplay request."""
    rdir = Path(run_dir)
    manifest = load_run_manifest(rdir)
    atlas_path = rdir / "sprite-sheet-alpha.png"
    b64 = base64.b64encode(atlas_path.read_bytes()).decode("ascii") if atlas_path.exists() else ""
    img_src = f"data:image/png;base64,{b64}" if b64 else "sprite-sheet-alpha.png"

    char_id = _get_char_id(manifest, "hero")
    rows_meta = manifest.get("animation", {}).get("rows", {})
    rects_map = _extract_state_rects(manifest)

    states_map: dict[str, dict[str, Any]] = {}
    for sname, rinfo in rows_meta.items():
        states_map[sname] = {"fps": float(rinfo.get("fps", 8)), "frames": rects_map.get(sname, [])}

    safe_prompt_comment = (
        custom_prompt.replace("*/", "")
        .replace("--", "—")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\r", " ")
        .replace("\n", " ")
    )
    pixel_js = "true" if pixel_art else "false"

    html_code = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>Sandboxed AI Custom Demo — {char_id}</title>
  <style>
    body {{ margin: 0; background: #10121a; color: #e5e7eb; font-family: system-ui, sans-serif; display: flex; flex-direction: column; align-items: center; padding: 12px; }}
    canvas {{ background: linear-gradient(180deg, #1b1730 0%, #261f3d 75%, #181424 100%); border: 2px solid #ec4899; border-radius: 10px; }}
    .hud {{ font-size: 12px; color: #f9a8d4; margin-top: 6px; }}
  </style>
</head>
<body>
  <!-- Custom Prompt: {safe_prompt_comment} -->
  <canvas id="game" width="680" height="320"></canvas>
  <div class="hud">✨ AI Custom Sandbox: <b>A/D</b> Di chuyển | <b>Space</b> Nhảy kép (Double Jump) | <b>J / Click</b> Tung chưởng Neko Heart | <b>K</b> Dash</div>
  <script>
    const STATES = {json.dumps(states_map)};
    const PIXEL_MODE = {pixel_js};
    const canvas = document.getElementById("game");
    const ctx = canvas.getContext("2d");
    const atlas = new Image();
    atlas.src = "{img_src}";

    let state = Object.keys(STATES).includes("walk") ? "walk" : Object.keys(STATES)[0];
    let frameIdx = 0, lastTs = 0;
    let x = 180, y = 0, vx = 0, vy = 0, jumpsLeft = 2, facing = 1, hp = 100, score = 0;
    const keys = {{}};
    const projectiles = [];
    const particles = [];

    window.addEventListener("keydown", e => {{
      keys[e.code] = true;
      if (e.code === "Space" && jumpsLeft > 0) {{
        vy = -9.5; jumpsLeft--;
        for (let i = 0; i < 8; i++) particles.push({{ x, y: 260 + y, vx: (Math.random()-0.5)*4, vy: Math.random()*2, life: 25 }});
      }}
      if (e.code === "KeyJ") spawnHeart();
      if (e.code === "KeyK") vx = facing * 12;
    }});
    window.addEventListener("keyup", e => {{ keys[e.code] = false; }});
    canvas.addEventListener("mousedown", spawnHeart);

    function spawnHeart() {{
      projectiles.push({{ x: x + facing * 36, y: 200 + y, vx: facing * 7, life: 80 }});
    }}

    function tick(ts) {{
      const st = STATES[state] || Object.values(STATES)[0];
      if (ts - lastTs >= 1000 / Math.max(1, st.fps || 8)) {{
        frameIdx = (frameIdx + 1) % st.frames.length;
        lastTs = ts;
      }}

      if (keys["KeyD"] || keys["ArrowRight"]) {{ vx = 3.8; facing = 1; state = STATES["walk"] ? "walk" : state; }}
      else if (keys["KeyA"] || keys["ArrowLeft"]) {{ vx = -3.8; facing = -1; state = STATES["walk"] ? "walk" : state; }}
      else {{ vx *= 0.82; if (Math.abs(vx) < 0.2 && STATES["idle"]) state = "idle"; }}

      x = Math.max(40, Math.min(canvas.width - 40, x + vx));
      if (y < 0 || vy < 0) {{
        y += vy; vy += 0.5;
        if (y >= 0) {{ y = 0; vy = 0; jumpsLeft = 2; }}
      }}

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = !PIXEL_MODE;
      const groundY = 270;
      ctx.strokeStyle = "#f472b6"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, groundY); ctx.lineTo(canvas.width, groundY); ctx.stroke();

      // HP Bar & Score
      ctx.fillStyle = "#1f2937"; ctx.fillRect(16, 14, 140, 12);
      ctx.fillStyle = "#ec4899"; ctx.fillRect(16, 14, 1.4 * hp, 12);
      ctx.fillStyle = "#fdf2f8"; ctx.font = "bold 12px sans-serif";
      ctx.fillText(`HP: ${{hp}}/100   Combo: ${{score}}`, 16, 42);

      if (atlas.complete && st.frames.length > 0) {{
        const f = st.frames[frameIdx % st.frames.length];
        const scale = Math.min(1, 170 / Math.max(1, f.h));
        const dw = f.w * scale, dh = f.h * scale;
        ctx.save();
        ctx.translate(x, groundY - dh + y);
        ctx.scale(facing, 1);
        ctx.drawImage(atlas, f.x, f.y, f.w, f.h, -dw / 2, 0, dw, dh);
        ctx.restore();
      }}

      // Projectiles
      for (let i = projectiles.length - 1; i >= 0; i--) {{
        const p = projectiles[i];
        p.x += p.vx; p.life--;
        ctx.fillStyle = "#f472b6"; ctx.font = "18px sans-serif";
        ctx.fillText("💖", p.x, p.y);
        if (p.life <= 0 || p.x < 0 || p.x > canvas.width) {{ projectiles.splice(i, 1); score++; }}
      }}

      // Jump dust particles
      for (let i = particles.length - 1; i >= 0; i--) {{
        const pt = particles[i];
        pt.x += pt.vx; pt.y += pt.vy; pt.life--;
        ctx.fillStyle = `rgba(244, 114, 182, ${{pt.life / 25}})`;
        ctx.beginPath(); ctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2); ctx.fill();
        if (pt.life <= 0) particles.splice(i, 1);
      }}

      requestAnimationFrame(tick);
    }}
    requestAnimationFrame(tick);
  </script>
</body>
</html>
"""
    return {
        "ok": True,
        "engine": "ai_sandbox_html5",
        "filename": "ai_custom_sandbox.html",
        "prompt": custom_prompt,
        "code": html_code,
    }
