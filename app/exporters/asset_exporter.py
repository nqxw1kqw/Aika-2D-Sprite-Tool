"""Asset Exporter: PNG Atlas, In-Place GIFs, Forward Auto-Run GIFs, and Aseprite JSON."""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.config import SPRITE_GEN_PYTHON, SPRITE_GEN_ROOT


def generate_forward_loop_gifs(
    run_dir: str | Path,
    state: str = "walk",
    velocity_px_per_step: int = 20,
) -> dict[str, Any]:
    """Generate both a Stage Forward Loop GIF (with shadow & ruler ticks) and Transparent Forward Loop GIF."""
    rdir = Path(run_dir)
    state_dir = rdir / "frames" / state
    if not state_dir.exists():
        # Fall back to first available state
        frames_root = rdir / "frames"
        candidates = [d for d in sorted(frames_root.iterdir()) if d.is_dir() and not d.name.startswith("_")] if frames_root.exists() else []
        if not candidates:
            return {"ok": False, "error": "No state frames found."}
        state_dir = candidates[0]
        state = state_dir.name

    png_files = sorted(state_dir.glob("frame-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    if not png_files:
        return {"ok": False, "error": f"No frames in {state_dir}"}

    src_frames = [Image.open(p).convert("RGBA") for p in png_files]
    fw, fh = src_frames[0].size

    out_previews = rdir / "previews"
    out_previews.mkdir(parents=True, exist_ok=True)

    total_steps = max(12, len(src_frames) * 3)
    canvas_w = max(560, fw * 2 + 120)
    canvas_h = fh + 40
    ground_y = fh - 8

    stage_frames: list[Image.Image] = []
    trans_dir = rdir / "_forward_temp"
    trans_dir.mkdir(parents=True, exist_ok=True)

    for step in range(total_steps):
        f_im = src_frames[step % len(src_frames)]
        x_pos = 16 + int(step * ((canvas_w - fw - 32) / max(1, total_steps - 1)))

        # 1. Stage frame with procedural ruler ticks & projected shadow
        stage = Image.new("RGBA", (canvas_w, canvas_h), (24, 24, 34, 255))
        draw = ImageDraw.Draw(stage)
        draw.line([(12, ground_y + 12), (canvas_w - 12, ground_y + 12)], fill=(120, 105, 145, 255), width=2)
        for tick_x in range(20, canvas_w - 20, 48):
            draw.line([(tick_x, ground_y + 12), (tick_x, ground_y + 20)], fill=(95, 85, 120, 255), width=2)

        # Projected soft ellipse shadow under character
        shadow_cx = x_pos + fw // 2
        shadow_rx = int(fw * 0.24)
        shadow_ry = max(4, int(fh * 0.035))
        draw.ellipse(
            [
                (shadow_cx - shadow_rx, ground_y + 6 - shadow_ry),
                (shadow_cx + shadow_rx, ground_y + 6 + shadow_ry),
            ],
            fill=(12, 10, 18, 150),
        )
        stage.paste(f_im, (x_pos, 12), f_im)
        stage_frames.append(stage.convert("RGB").quantize(colors=256))

        # 2. Transparent frame
        trans = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        trans.paste(f_im, (x_pos, 12), f_im)
        trans.save(trans_dir / f"frame-{step:02d}.png")

    stage_gif_path = out_previews / f"{state}_forward_stage.gif"
    stage_frames[0].save(
        stage_gif_path,
        save_all=True,
        append_images=stage_frames[1:],
        duration=85,
        loop=0,
    )

    trans_gif_path = out_previews / f"{state}_forward_transparent.gif"
    compose_gif_script = SPRITE_GEN_ROOT / "scripts" / "compose_sprite_gif.py"
    trans_pngs = sorted(glob.glob(str(trans_dir / "frame-*.png")))
    import subprocess

    subprocess.run(
        [str(SPRITE_GEN_PYTHON), str(compose_gif_script), *trans_pngs, "--output", str(trans_gif_path), "--delay-ticks", "9"],
        capture_output=True,
        timeout=60,
    )

    return {
        "ok": True,
        "state": state,
        "stage_gif": str(stage_gif_path),
        "transparent_gif": str(trans_gif_path),
    }


def export_assets_bundle(run_dir: str | Path, out_dir: str | Path) -> dict[str, Any]:
    """Export PNG sprite sheet, manifest.json, individual frames, and forward-loop GIFs into out_dir."""
    import shutil

    rdir = Path(run_dir)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)

    for fname in ("sprite-sheet-alpha.png", "manifest.json", "curation.json"):
        src_f = rdir / fname
        if src_f.exists():
            shutil.copy2(src_f, dest / fname)

    if (rdir / "frames").exists():
        frames_dst = dest / "frames"
        if frames_dst.exists():
            shutil.rmtree(frames_dst)
        shutil.copytree(rdir / "frames", frames_dst)

    gif_res = generate_forward_loop_gifs(rdir, state="walk")
    if (rdir / "previews").exists():
        prev_dst = dest / "previews"
        if prev_dst.exists():
            shutil.rmtree(prev_dst)
        shutil.copytree(rdir / "previews", prev_dst)

    return {"ok": True, "bundle_dir": str(dest), "gifs": gif_res}
