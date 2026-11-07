"""Instant 0-second Code Exporter (`template_codegen.py`).

Generates ready-to-run code from `manifest.json` for:
1. HTML5 Canvas (`html5`): Self-contained single-file `.html` with embedded Base64 sprite sheet,
   Crisp Pixel Art / Smooth HD toggle, In-Place & Forward Auto-Run Stage, and Keyboard Controls.
2. Phaser 3 (`phaser3`): Complete `Phaser.Scene` ES6 script with `anims.create`.
3. Godot 4 (`godot4`): Complete `CharacterBody2D` GDScript (`.gd`) with animation state logic.
4. Unity C# (`unity`): Complete `MonoBehaviour` Sprite Sheet Animator & Controller (`SpriteAutoRunner.cs`).
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any


def _validate_manifest_structure(data: dict[str, Any], rdir: Path) -> None:
    """Validate required animation/cell/frame_layout fields in manifest.json."""
    cell = data.get("cell")
    if cell is not None:
        if not isinstance(cell, dict):
            raise ValueError(f"manifest.json 'cell' in {rdir} must be an object")
        cw = int(cell.get("width", 256))
        ch = int(cell.get("height", 256))
        if cw < 1 or ch < 1:
            raise ValueError(f"manifest.json 'cell' dimensions in {rdir} must be >= 1")

    anim = data.get("animation")
    if not isinstance(anim, dict):
        raise ValueError(f"manifest.json in {rdir} is missing an 'animation' object")
    rows = anim.get("rows")
    if not isinstance(rows, dict) or not rows:
        raise ValueError(f"manifest.json in {rdir} must contain a non-empty 'animation.rows' object")
    for sname, rinfo in rows.items():
        if not sname or not isinstance(rinfo, dict):
            raise ValueError(f"manifest.json 'animation.rows.{sname}' in {rdir} must be an object")
        fps = float(rinfo.get("fps", 8))
        frames = int(rinfo.get("frames", 4))
        if fps <= 0 or frames < 1:
            raise ValueError(f"manifest.json state '{sname}' in {rdir} must have fps > 0 and frames >= 1")

    fl = data.get("frame_layout")
    if fl is not None:
        if not isinstance(fl, dict):
            raise ValueError(f"manifest.json 'frame_layout' in {rdir} must be an object")
        if fl.get("rows") is not None and not isinstance(fl.get("rows"), dict):
            raise ValueError(f"manifest.json 'frame_layout.rows' in {rdir} must be an object")
        if fl.get("frames") is not None and not isinstance(fl.get("frames"), list):
            raise ValueError(f"manifest.json 'frame_layout.frames' in {rdir} must be a list")


def load_run_manifest(run_dir: str | Path) -> dict[str, Any]:
    """Read and validate manifest.json from a sprite-gen run directory."""
    rdir = Path(run_dir)
    mpath = rdir / "manifest.json"
    if not mpath.exists():
        raise FileNotFoundError(f"manifest.json not found in {rdir}")
    data = json.loads(mpath.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest.json in {rdir} must contain a JSON object, got {type(data).__name__}")
    _validate_manifest_structure(data, rdir)
    return data


def _get_char_id(manifest: dict[str, Any], default: str = "sprite_actor") -> str:
    raw: str | None = None
    for key in ("characterId", "character_id"):
        if key in manifest and manifest[key]:
            raw = str(manifest[key])
            break
    if raw is None:
        char_obj = manifest.get("character")
        if isinstance(char_obj, dict) and char_obj.get("id"):
            raw = str(char_obj["id"])
    if not raw:
        return default
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", raw).strip("_")
    return cleaned or default


def _extract_state_rects(manifest: dict[str, Any]) -> dict[str, list[dict[str, int]]]:
    cell = manifest.get("cell") or {"width": 256, "height": 256}
    cw, ch = int(cell.get("width", 256)), int(cell.get("height", 256))
    rows_meta = manifest.get("animation", {}).get("rows", {})
    frame_layout = manifest.get("frame_layout") or {}
    layout_rows = frame_layout.get("rows") or {}
    layout_frames = frame_layout.get("frames") or []

    out: dict[str, list[dict[str, int]]] = {st: [] for st in rows_meta}
    for st, rlist in layout_rows.items():
        if not isinstance(rlist, list):
            raise ValueError(f"frame_layout.rows.{st} must be a list")
        out[st] = [
            {
                "x": int(rf.get("x", 0)),
                "y": int(rf.get("y", 0)),
                "w": int(rf.get("w", rf.get("width", cw))),
                "h": int(rf.get("h", rf.get("height", ch))),
            }
            for rf in rlist
        ]
    for lf in layout_frames:
        if not isinstance(lf, dict):
            raise ValueError("frame_layout.frames entries must be objects")
        st = str(lf.get("state", "idle"))
        out.setdefault(st, []).append(
            {
                "x": int(lf.get("x", 0)),
                "y": int(lf.get("y", 0)),
                "w": int(lf.get("w", lf.get("width", cw))),
                "h": int(lf.get("h", lf.get("height", ch))),
            }
        )
    # Synthesize grid coordinates if frame_layout was omitted for any declared animation row
    for row_idx, (st, rinfo) in enumerate(rows_meta.items()):
        if not out.get(st):
            r_idx = int(rinfo.get("row", row_idx))
            fcount = int(rinfo.get("frames", 4))
            out[st] = [
                {"x": i * cw, "y": r_idx * ch, "w": cw, "h": ch}
                for i in range(fcount)
            ]
    return out


def generate_html5_canvas_code(
    run_dir: str | Path,
    embed_base64: bool = True,
    default_pixel_art: bool = False,
) -> str:
    """Generate a standalone, self-contained HTML5 Canvas game/preview file from manifest.json."""
    rdir = Path(run_dir)
    manifest = load_run_manifest(rdir)
    atlas_path = rdir / "sprite-sheet-alpha.png"

    if embed_base64 and atlas_path.exists():
        b64 = base64.b64encode(atlas_path.read_bytes()).decode("ascii")
        img_src = f"data:image/png;base64,{b64}"
    else:
        img_src = "sprite-sheet-alpha.png"

    char_id = _get_char_id(manifest, "sprite_actor")
    cell = manifest.get("cell") or {"width": 256, "height": 256}
    cell_w = int(cell.get("width", 256))
    cell_h = int(cell.get("height", 256))
    rows_meta = manifest.get("animation", {}).get("rows", {})
    rects_map = _extract_state_rects(manifest)

    # Group frame boxes by state
    states_map: dict[str, dict[str, Any]] = {}
    for sname, rinfo in rows_meta.items():
        states_map[sname] = {
            "fps": float(rinfo.get("fps", 8)),
            "loop": bool(rinfo.get("loop", True)),
            "frames": rects_map.get(sname, []),
        }

    states_json = json.dumps(states_map, indent=2)
    pixel_bool = "true" if default_pixel_art else "false"

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <title>2D Sprite Auto-Run — {char_id}</title>
  <style>
    body {{
      margin: 0; background: #12131a; color: #f3f4f6;
      font-family: system-ui, -apple-system, sans-serif;
      display: flex; flex-direction: column; align-items: center; padding: 24px;
    }}
    .toolbar {{
      display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px;
      background: #1e2030; padding: 10px 16px; border-radius: 10px; border: 1px solid #333852;
    }}
    button, select {{
      background: #2b3048; color: #fff; border: 1px solid #454d70;
      padding: 6px 12px; border-radius: 6px; cursor: pointer; font-weight: 600;
    }}
    button.active {{ background: #ec4899; border-color: #f472b6; }}
    canvas {{
      background: #181a26; border: 2px solid #383e5c; border-radius: 12px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.45);
    }}
    canvas.pixelated {{ image-rendering: pixelated; image-rendering: crisp-edges; }}
    .hint {{ margin-top: 10px; font-size: 13px; color: #9ca3af; }}
  </style>
</head>
<body>
  <h2>🎮 2D Sprite Auto-Run Player — <code>{char_id}</code></h2>
  <div class="toolbar">
    <label>State: <select id="stateSelect"></select></label>
    <button id="modeBtn" class="active">🏃 Mode: Forward Auto-Run</button>
    <button id="pixelBtn">👾 Crisp Pixel Art</button>
    <button id="zoomBtn">🔍 Zoom: 1x</button>
  </div>
  <canvas id="stage" width="720" height="360"></canvas>
  <div class="hint">Phím tắt: <b>A / D</b> hoặc <b>◀ / ▶</b> để di chuyển, <b>Space</b> để nhảy, hoặc để nhân vật tự chạy Auto-Run Looping!</div>

  <script>
    const STATES = {states_json};
    const CELL_W = {cell_w}, CELL_H = {cell_h};
    let currentState = Object.keys(STATES).includes("walk") ? "walk" : Object.keys(STATES)[0];
    let forwardMode = true;
    let pixelMode = {pixel_bool};
    let zoom = 1;
    let frameIdx = 0, lastFrameTime = 0, scrollX = 0;
    let actorX = 260, actorY = 0, vy = 0, facing = 1;
    const keys = {{}};

    const canvas = document.getElementById("stage");
    const ctx = canvas.getContext("2d");
    const stateSelect = document.getElementById("stateSelect");

    Object.keys(STATES).forEach(s => {{
      const opt = document.createElement("option");
      opt.value = s; opt.textContent = s;
      if (s === currentState) opt.selected = true;
      stateSelect.appendChild(opt);
    }});

    stateSelect.onchange = e => {{ currentState = e.target.value; frameIdx = 0; }};
    document.getElementById("modeBtn").onclick = e => {{
      forwardMode = !forwardMode;
      e.target.textContent = forwardMode ? "🏃 Mode: Forward Auto-Run" : "🧍 Mode: In-Place Loop";
      e.target.classList.toggle("active", forwardMode);
    }};
    const pixelBtn = document.getElementById("pixelBtn");
    function syncPixelMode() {{
      canvas.classList.toggle("pixelated", pixelMode);
      pixelBtn.classList.toggle("active", pixelMode);
    }}
    syncPixelMode();
    pixelBtn.onclick = () => {{ pixelMode = !pixelMode; syncPixelMode(); }};

    document.getElementById("zoomBtn").onclick = e => {{
      const zooms = [1, 2, 3];
      zoom = zooms[(zooms.indexOf(zoom) + 1) % zooms.length];
      e.target.textContent = `🔍 Zoom: ${{zoom}}x`;
    }};

    window.addEventListener("keydown", e => {{
      keys[e.code] = true;
      if (e.code === "Space" && actorY === 0) vy = -10;
    }});
    window.addEventListener("keyup", e => {{ keys[e.code] = false; }});

    const atlas = new Image();
    atlas.src = "{img_src}";

    function loop(ts) {{
      const st = STATES[currentState] || Object.values(STATES)[0];
      const interval = 1000 / Math.max(1, st.fps || 8);
      if (ts - lastFrameTime >= interval) {{
        frameIdx = (frameIdx + 1) % st.frames.length;
        lastFrameTime = ts;
      }}

      // Keyboard or Auto-Run physics
      if (keys["ArrowRight"] || keys["KeyD"]) {{ facing = 1; scrollX += 3; }}
      else if (keys["ArrowLeft"] || keys["KeyA"]) {{ facing = -1; scrollX -= 3; }}
      else if (forwardMode) {{ scrollX += 2.6; }}

      if (actorY < 0 || vy < 0) {{
        actorY += vy; vy += 0.55;
        if (actorY >= 0) {{ actorY = 0; vy = 0; }}
      }}

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.imageSmoothingEnabled = !pixelMode;

      const groundY = canvas.height - 48;
      // Draw procedural stage & scrolling ruler ticks
      ctx.strokeStyle = "#4b5563"; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(0, groundY); ctx.lineTo(canvas.width, groundY); ctx.stroke();

      const tickSpacing = 64;
      const offset = ((scrollX % tickSpacing) + tickSpacing) % tickSpacing;
      ctx.fillStyle = "#6b7280"; ctx.font = "11px monospace";
      for (let x = -offset; x < canvas.width; x += tickSpacing) {{
        ctx.beginPath(); ctx.moveTo(x, groundY); ctx.lineTo(x, groundY + 10); ctx.stroke();
      }}

      if (atlas.complete && st.frames.length > 0) {{
        const f = st.frames[frameIdx % st.frames.length];
        const drawW = Math.round(f.w * zoom), drawH = Math.round(f.h * zoom);
        const cx = canvas.width / 2;
        const cy = groundY - drawH + actorY;

        // Projected shadow on ground
        ctx.fillStyle = "rgba(10, 10, 18, 0.45)";
        ctx.beginPath();
        ctx.ellipse(cx, groundY - 2, drawW * 0.22, Math.max(4, drawH * 0.04), 0, 0, Math.PI * 2);
        ctx.fill();

        ctx.save();
        ctx.translate(cx, cy);
        ctx.scale(facing, 1);
        ctx.drawImage(atlas, f.x, f.y, f.w, f.h, -drawW / 2, 0, drawW, drawH);
        ctx.restore();
      }}
      requestAnimationFrame(loop);
    }}
    requestAnimationFrame(loop);
  </script>
</body>
</html>
"""


def generate_phaser3_code(run_dir: str | Path) -> str:
    """Generate Phaser 3 Scene code consuming sprite-sheet-alpha.png and manifest.json."""
    manifest = load_run_manifest(run_dir)
    char_id = _get_char_id(manifest, "hero")
    cell = manifest.get("cell") or {"width": 256, "height": 256}
    cw, ch = int(cell.get("width", 256)), int(cell.get("height", 256))
    rows_meta = manifest.get("animation", {}).get("rows", {})
    max_cols = max((int(r.get("frames", 1)) for r in rows_meta.values()), default=1)

    anims_js: list[str] = []
    for row_idx, (sname, rinfo) in enumerate(rows_meta.items()):
        fcount = int(rinfo.get("frames", 4))
        fps = float(rinfo.get("fps", 8))
        repeat = -1 if rinfo.get("loop", True) else 0
        start_f = row_idx * max_cols
        end_f = start_f + fcount - 1
        anims_js.append(
            f"""    this.anims.create({{
      key: '{sname}',
      frames: this.anims.generateFrameNumbers('{char_id}', {{ start: {start_f}, end: {end_f} }}),
      frameRate: {fps},
      repeat: {repeat}
    }});"""
        )

    default_state = "walk" if "walk" in rows_meta else next(iter(rows_meta.keys()), "idle")
    anims_block = "\n".join(anims_js)

    return f"""// Phaser 3 Auto-Generated Sprite Scene for `{char_id}`
import Phaser from 'phaser';

export class SpritePreviewScene extends Phaser.Scene {{
  constructor() {{
    super('SpritePreviewScene');
  }}

  preload() {{
    // Ensure Pixel Art mode in game config: render: {{ pixelArt: true }}
    this.load.spritesheet('{char_id}', 'sprite-sheet-alpha.png', {{
      frameWidth: {cw},
      frameHeight: {ch}
    }});
  }}

  create() {{
{anims_block}

    this.actor = this.add.sprite(400, 300, '{char_id}');
    this.actor.play('{default_state}');
    this.cursors = this.input.keyboard.createCursorKeys();
  }}

  update() {{
    if (this.cursors.left.isDown) {{
      this.actor.setFlipX(true);
      this.actor.x -= 3;
    }} else if (this.cursors.right.isDown) {{
      this.actor.setFlipX(false);
      this.actor.x += 3;
    }}
  }}
}}
"""


def generate_godot4_code(run_dir: str | Path) -> str:
    """Generate Godot 4 CharacterBody2D GDScript with AtlasTexture frame rectangles."""
    manifest = load_run_manifest(run_dir)
    char_id = _get_char_id(manifest, "hero")
    rows_meta = manifest.get("animation", {}).get("rows", {})
    rects_map = _extract_state_rects(manifest)

    states_dict: dict[str, Any] = {}
    for sname, rinfo in rows_meta.items():
        states_dict[sname] = {
            "fps": float(rinfo.get("fps", 8)),
            "loop": bool(rinfo.get("loop", True)),
            "rects": [[r["x"], r["y"], r["w"], r["h"]] for r in rects_map.get(sname, [])],
        }

    return f"""# Godot 4 CharacterBody2D Script for `{char_id}`
# Attach to a CharacterBody2D node with an AnimatedSprite2D child named `AnimatedSprite2D`.
extends CharacterBody2D

const SPEED: float = 220.0
const JUMP_VELOCITY: float = -380.0
const ATLAS_PATH: String = "res://sprite-sheet-alpha.png"

const ANIM_DATA = {json.dumps(states_dict, indent=2)}

@onready var anim_sprite: AnimatedSprite2D = $AnimatedSprite2D

func _ready() -> void:
\t# Crisp pixel art filter:
\tanim_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
\t_build_sprite_frames()
\tanim_sprite.play("walk" if ANIM_DATA.has("walk") else ANIM_DATA.keys()[0])

func _build_sprite_frames() -> void:
\tvar tex: Texture2D = load(ATLAS_PATH)
\tvar sf := SpriteFrames.new()
\tfor state_name in ANIM_DATA.keys():
\t\tvar info = ANIM_DATA[state_name]
\t\tsf.add_animation(state_name)
\t\tsf.set_animation_speed(state_name, info["fps"])
\t\tsf.set_animation_loop(state_name, info["loop"])
\t\tfor r in info["rects"]:
\t\t\tvar at := AtlasTexture.new()
\t\t\tat.atlas = tex
\t\t\tat.region = Rect2(r[0], r[1], r[2], r[3])
\t\t\tsf.add_frame(state_name, at)
\tanim_sprite.sprite_frames = sf

func _physics_process(delta: float) -> void:
\tif not is_on_floor():
\t\tvelocity += get_gravity() * delta
\tif Input.is_action_just_pressed("ui_accept") and is_on_floor():
\t\tvelocity.y = JUMP_VELOCITY
\tvar dir := Input.get_axis("ui_left", "ui_right")
\tif dir != 0:
\t\tvelocity.x = dir * SPEED
\t\tanim_sprite.flip_h = (dir < 0)
\t\tif ANIM_DATA.has("walk"):
\t\t\tanim_sprite.play("walk")
\telse:
\t\tvelocity.x = move_toward(velocity.x, 0, SPEED)
\t\tif ANIM_DATA.has("idle"):
\t\t\tanim_sprite.play("idle")
\tmove_and_slide()
"""


def generate_unity_csharp_code(run_dir: str | Path) -> str:
    """Generate Unity C# MonoBehaviour script for animating the sprite sheet."""
    manifest = load_run_manifest(run_dir)
    char_id = _get_char_id(manifest, "Hero")
    cell = manifest.get("cell") or {"width": 256, "height": 256}
    cw, ch = int(cell.get("width", 256)), int(cell.get("height", 256))
    rows_meta = manifest.get("animation", {}).get("rows", {})

    states_lines: list[str] = []
    for idx, (sname, rinfo) in enumerate(rows_meta.items()):
        fcount = int(rinfo.get("frames", 4))
        fps = float(rinfo.get("fps", 8))
        states_lines.append(f'        {{ "{sname}", new AnimRow({idx}, {fcount}, {fps}f) }},')
    states_init = "\n".join(states_lines)

    return f"""// Unity C# Sprite Sheet Auto-Runner for `{char_id}`
using System.Collections.Generic;
using UnityEngine;

[RequireComponent(typeof(SpriteRenderer))]
public class SpriteAutoRunner : MonoBehaviour
{{
    public Texture2D atlasTexture;
    public int cellWidth = {cw};
    public int cellHeight = {ch};
    public string currentState = "{"walk" if "walk" in rows_meta else "idle"}";
    public float moveSpeed = 3.5f;

    private struct AnimRow
    {{
        public int rowIndex;
        public int frameCount;
        public float fps;
        public AnimRow(int r, int c, float f) {{ rowIndex = r; frameCount = c; fps = f; }}
    }}

    private readonly Dictionary<string, AnimRow> _rows = new Dictionary<string, AnimRow>
    {{
{states_init}
    }};

    private SpriteRenderer _sr;
    private Dictionary<string, Sprite[]> _sprites = new Dictionary<string, Sprite[]>();
    private float _timer;
    private int _frameIdx;

    void Awake()
    {{
        _sr = GetComponent<SpriteRenderer>();
        if (atlasTexture == null) return;
        atlasTexture.filterMode = FilterMode.Point; // Crisp Pixel Art
        int totalRows = _rows.Count;
        foreach (var kv in _rows)
        {{
            var row = kv.Value;
            var arr = new Sprite[row.frameCount];
            int yTop = atlasTexture.height - (row.rowIndex + 1) * cellHeight;
            for (int i = 0; i < row.frameCount; i++)
            {{
                Rect rect = new Rect(i * cellWidth, yTop, cellWidth, cellHeight);
                arr[i] = Sprite.Create(atlasTexture, rect, new Vector2(0.5f, 0f), 100f);
            }}
            _sprites[kv.Key] = arr;
        }}
    }}

    void Update()
    {{
        if (!_sprites.ContainsKey(currentState)) return;
        var row = _rows[currentState];
        _timer += Time.deltaTime;
        if (_timer >= 1f / row.fps)
        {{
            _timer = 0f;
            _frameIdx = (_frameIdx + 1) % row.frameCount;
            _sr.sprite = _sprites[currentState][_frameIdx];
        }}

        float h = Input.GetAxisRaw("Horizontal");
        if (Mathf.Abs(h) > 0.01f)
        {{
            _sr.flipX = h < 0;
            transform.Translate(Vector3.right * (h * moveSpeed * Time.deltaTime));
        }}
    }}
}}
"""


def generate_dxlib_cpp_code(run_dir: str | Path) -> str:
    """Generate a ready-to-compile C++ & DxLib (DxLib.h) 60fps Sprite Auto-Runner."""
    manifest = load_run_manifest(run_dir)
    char_id = _get_char_id(manifest, "jirai_neko")
    rows_meta = manifest.get("animation", {}).get("rows", {})
    rects_map = _extract_state_rects(manifest)

    states_map: dict[str, list[tuple[int, int, int, int]]] = {}
    fps_map: dict[str, float] = {}
    for sname, rinfo in rows_meta.items():
        fps_map[sname] = float(rinfo.get("fps", 8.0))
        states_map[sname] = [(r["x"], r["y"], r["w"], r["h"]) for r in rects_map.get(sname, [])]

    state_Blocks: list[str] = []
    for sname, rects in states_map.items():
        rect_strs = ", ".join(f"{{{x}, {y}, {w}, {h}}}" for (x, y, w, h) in rects)
        state_Blocks.append(
            f'        {{ "{sname}", {{ {fps_map.get(sname, 8.0)}f, {{ {rect_strs} }} }} }},'
        )
    states_init = "\n".join(state_Blocks)
    default_st = "walk" if "walk" in states_map else next(iter(states_map.keys()), "idle")

    return f"""// C++ & DxLib 2D Sprite Auto-Runner for `{char_id}`
// Compile with Visual Studio + C:\\DxLib_Normal (64-bit /MT)
#include "DxLib.h"
#include <map>
#include <string>
#include <vector>

struct FrameRect {{ int x, y, w, h; }};
struct AnimState {{
    float fps;
    std::vector<FrameRect> frames;
}};

int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {{
    ChangeWindowMode(TRUE);
    SetGraphMode(960, 540, 32);
    SetMainWindowText("DxLib 2D Sprite Auto-Run - {char_id}");
    if (DxLib_Init() == -1) return -1;
    SetDrawScreen(DX_SCREEN_BACK);

    int atlasHandle = LoadGraph("sprite-sheet-alpha.png");
    std::map<std::string, AnimState> states = {{
{states_init}
    }};

    std::string currentState = "{default_st}";
    bool pixelArtMode = false;
    bool forwardLoop = true;
    int zoom = 1;
    float actorX = 480.0f, actorY = 0.0f, vy = 0.0f, scrollX = 0.0f;
    bool flipX = false;
    int frameIdx = 0;
    int lastTick = GetNowCount();

    while (ProcessMessage() == 0 && CheckHitKey(KEY_INPUT_ESCAPE) == 0) {{
        ClearDrawScreen();

        // Keyboard controls: A/D or Left/Right to move, Space to jump, P to toggle Pixel Art
        if (CheckHitKey(KEY_INPUT_RIGHT) || CheckHitKey(KEY_INPUT_D)) {{
            flipX = false; scrollX += 4.0f;
            if (states.count("walk")) currentState = "walk";
        }} else if (CheckHitKey(KEY_INPUT_LEFT) || CheckHitKey(KEY_INPUT_A)) {{
            flipX = true; scrollX -= 4.0f;
            if (states.count("walk")) currentState = "walk";
        }} else if (forwardLoop) {{
            scrollX += 3.0f;
        }}

        if (CheckHitKey(KEY_INPUT_SPACE) && actorY == 0.0f) vy = -11.0f;
        if (actorY < 0.0f || vy < 0.0f) {{
            actorY += vy; vy += 0.55f;
            if (actorY >= 0.0f) {{ actorY = 0.0f; vy = 0.0f; }}
        }}

        const AnimState& st = states[currentState];
        int now = GetNowCount();
        int intervalMs = (int)(1000.0f / (st.fps > 0.0f ? st.fps : 8.0f));
        if (!st.frames.empty() && now - lastTick >= intervalMs) {{
            frameIdx = (frameIdx + 1) % (int)st.frames.size();
            lastTick = now;
        }}

        // Draw procedural ground & scrolling 64px ruler ticks
        int groundY = 460;
        DrawLine(0, groundY, 960, groundY, GetColor(110, 100, 145), 2);
        int offset = ((int)scrollX % 64 + 64) % 64;
        for (int tx = -offset; tx < 960; tx += 64) {{
            DrawLine(tx, groundY, tx, groundY + 10, GetColor(85, 80, 115), 2);
        }}

        if (atlasHandle != -1 && !st.frames.empty()) {{
            const FrameRect& fr = st.frames[frameIdx % st.frames.size()];
            int subH = DerivationGraph(fr.x, fr.y, fr.w, fr.h, atlasHandle);
            int drawW = fr.w * zoom;
            int drawH = fr.h * zoom;
            int topY = groundY - drawH + (int)actorY;

            // Projected dynamic shadow
            SetDrawBlendMode(DX_BLENDMODE_ALPHA, 120);
            DrawOval((int)actorX, groundY - 2, (int)(drawW * 0.22f), 7, GetColor(10, 10, 18), TRUE);
            SetDrawBlendMode(DX_BLENDMODE_NOBLEND, 0);

            SetDrawMode(pixelArtMode ? DX_DRAWMODE_NEAREST : DX_DRAWMODE_BILINEAR);
            if (!flipX) {{
                DrawExtendGraph((int)actorX - drawW / 2, topY, (int)actorX + drawW / 2, topY + drawH, subH, TRUE);
            }} else {{
                DrawExtendGraph((int)actorX + drawW / 2, topY, (int)actorX - drawW / 2, topY + drawH, subH, TRUE);
            }}
            DeleteGraph(subH);
        }}

        DrawFormatString(20, 20, GetColor(244, 114, 182),
            "DxLib Sprite Auto-Run [%s] | State: %s | Frame: %d/%d | A/D: Move, Space: Jump, ESC: Quit",
            "{char_id}", currentState.c_str(), frameIdx + 1, (int)st.frames.size());

        ScreenFlip();
    }}

    DxLib_End();
    return 0;
}}
"""


_ENGINE_TARGETS: dict[str, tuple[str, str]] = {
    "dxlib": ("dxlib_sprite_runner.cpp", "cpp"),
    "html5": ("sprite_autorun_player.html", "html"),
    "phaser3": ("SpritePreviewScene.js", "javascript"),
    "godot4": ("CharacterAutoRunner.gd", "gdscript"),
    "unity": ("SpriteAutoRunner.cs", "csharp"),
}

SUPPORTED_ENGINES: tuple[str, ...] = tuple(_ENGINE_TARGETS)


def export_code_by_engine(
    run_dir: str | Path,
    engine: str = "html5",
    embed_base64: bool = True,
    pixel_art: bool = False,
) -> dict[str, Any]:
    """Generate code for the requested engine and return filename + source code.

    Never raises for bad input: returns `{"ok": False, "error_code": ..., "error": ...}` with
    `UNSUPPORTED_ENGINE`, `MANIFEST_NOT_FOUND` or `MANIFEST_INVALID`.
    """
    eng = engine.lower().strip()
    if eng not in _ENGINE_TARGETS:
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_ENGINE",
            "error": f"Unsupported engine: {engine}. Supported: {', '.join(SUPPORTED_ENGINES)}",
        }

    try:
        if eng == "dxlib":
            code = generate_dxlib_cpp_code(run_dir)
        elif eng == "html5":
            code = generate_html5_canvas_code(run_dir, embed_base64=embed_base64, default_pixel_art=pixel_art)
        elif eng == "phaser3":
            code = generate_phaser3_code(run_dir)
        elif eng == "godot4":
            code = generate_godot4_code(run_dir)
        else:
            code = generate_unity_csharp_code(run_dir)
    except FileNotFoundError as exc:
        return {"ok": False, "error_code": "MANIFEST_NOT_FOUND", "error": str(exc)}
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        # json.JSONDecodeError is a ValueError; the others come from unexpected manifest shapes.
        return {
            "ok": False,
            "error_code": "MANIFEST_INVALID",
            "error": f"manifest.json is malformed ({type(exc).__name__}: {exc})",
        }

    filename, language = _ENGINE_TARGETS[eng]
    return {"ok": True, "engine": eng, "filename": filename, "language": language, "code": code}
