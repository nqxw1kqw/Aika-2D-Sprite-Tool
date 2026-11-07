"""CLI Bridge for the Native C++ DxLib Desktop App (`AikaSpriteStudioDxLib.exe`).

Provides complete backend actions for the 5-Tab User Menu Hub:
1. `sync`: Export `dxlib_meta.txt` with project runs, inputs list, auto-detector report, and frame metrics.
2. `import_file`: Import an external image (.png/.jpg/.webp) into `inputs/`, set active, and analyze.
3. `select_input`: Switch active input image in `inputs/` and analyze.
4. `cutout`: 1-Click background cutout for opaque reference images (`OPAQUE_WALL` gate recovery).
5. `drop`: Import dropped image and immediately run `work`.
6. `work`: Smart Auto-Detect WORK (2s Slice for sprite sheets, Codex AI for single stills).
7. `slice_sheet`: Force slice/unpack active input into state rows (`idle,walk`, etc.).
8. `ai_regen`: Run Codex CLI + `sprite-gen` pipeline with custom states & chroma key.
9. `reroll_state`: Re-roll a single animation state row (`idle`, `walk`, etc.).
10. `inbetween`: Generate an AI/optical-flow interpolated frame between `frame` and `frame+1`.
11. `seamless_bg`: Convert active input into a seamless horizontally tileable stage background.
12. `stabilize`: Run 1-Click Auto-Stabilize + Idle Breathe (`smooth` or `pixel`).
13. `reset`: Remove `curation.json` and restore original frames.
14. `nudge`: Adjust a frame's `dx`, `dy` or `selected` flag.
15. `set_fps`: Change animation state FPS in `manifest.json`.
16. `export`: Export C++ DxLib, HTML5, Phaser 3, Godot 4, Unity C#, or full Asset Bundle.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from app.config import PROJECTS_DIR
from app.core.auto_stabilizer import apply_auto_stabilize, apply_manual_frame_edit
from app.core.detector import analyze_input_image
from app.core.frame_analyzer import analyze_run_directory
from app.core.pipeline_runner import (
    build_states_spec,
    interpolate_inbetween_frame,
    make_seamless_background_tile,
    recompose_run,
    reroll_single_state,
    run_ai_sprite_pipeline,
    unpack_existing_sheet,
)
from app.exporters.asset_exporter import export_assets_bundle
from app.exporters.template_codegen import export_code_by_engine, load_run_manifest
from app.project_manager import ensure_default_demo_project, get_project_details, update_project_meta


def perform_auto_cutout(src_path: Path, dst_path: Path, tolerance: float = 42.0) -> Path:
    """Remove solid/corner background from an opaque image and save as RGBA PNG."""
    img = Image.open(src_path).convert("RGBA")
    arr = np.asarray(img, dtype=np.float32)
    h, w, _ = arr.shape
    patch = max(2, min(10, h // 12, w // 12))
    corners = np.concatenate(
        [
            arr[:patch, :patch, :3].reshape(-1, 3),
            arr[:patch, -patch:, :3].reshape(-1, 3),
            arr[-patch:, :patch, :3].reshape(-1, 3),
            arr[-patch:, -patch:, :3].reshape(-1, 3),
        ],
        axis=0,
    )
    bg_rgb = np.median(corners, axis=0)
    dist = np.linalg.norm(arr[:, :, :3] - bg_rgb[None, None, :], axis=2)

    out = np.asarray(img, dtype=np.uint8).copy()
    mask_bg = dist < tolerance
    out[mask_bg, 3] = 0
    # Soft feather edge
    feather = (dist >= tolerance) & (dist < tolerance + 14.0)
    if np.any(feather):
        alpha_scale = (dist[feather] - tolerance) / 14.0
        out[feather, 3] = np.clip(out[feather, 3].astype(np.float32) * alpha_scale, 0, 255).astype(np.uint8)

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out, mode="RGBA").save(dst_path)
    return dst_path


def write_dxlib_meta(project_id: str, run_id: str | None = None) -> Path:
    """Write a comprehensive, line-oriented `dxlib_meta.txt` file for fast C++ parsing."""
    ensure_default_demo_project()
    details = get_project_details(project_id)
    pdir = PROJECTS_DIR / project_id

    active_run = run_id or details.get("active_run") or "codex_run"
    rdir = pdir / "runs" / active_run
    if not (rdir / "manifest.json").exists():
        runs_root = pdir / "runs"
        for cand in sorted(runs_root.iterdir()):
            if (cand / "manifest.json").exists():
                rdir = cand
                active_run = cand.name
                break

    raw_inputs = details.get("inputs", []) or ["input_sheet.png"]
    inputs_list = [inp["name"] if isinstance(inp, dict) else str(inp) for inp in raw_inputs]
    active_input = details.get("active_input") or inputs_list[0]
    inp_path = (pdir / "inputs" / active_input).resolve()
    if not inp_path.exists() and inputs_list:
        active_input = inputs_list[0]
        inp_path = (pdir / "inputs" / active_input).resolve()

    det = analyze_input_image(inp_path) if inp_path.exists() else {"ok": False, "kind": "missing"}
    det_ok = 1 if det.get("ok") else 0
    det_kind = str(det.get("kind") or "unknown")
    det_w = int(det.get("width", 0))
    det_h = int(det.get("height", 0))
    grid = det.get("grid") or {}
    det_rows = int(grid.get("rows", 1))
    det_cols = int(grid.get("cols", 1))
    det_alpha = 1 if det.get("has_transparent_bg") else 0
    det_chroma = str(det.get("recommended_chroma_key") or "#00FF00")
    det_err = str(det.get("error_code") or "NONE")
    det_msg = str(det.get("message") or det.get("action_Required") or "Ready for pipeline").replace("\n", " ")

    manifest = load_run_manifest(rdir)
    analysis = analyze_run_directory(rdir)
    atlas_path = (rdir / "sprite-sheet-alpha.png").resolve()

    curation_states: dict = {}
    curation_path = rdir / "curation.json"
    if curation_path.exists():
        try:
            curation_states = json.loads(curation_path.read_text(encoding="utf-8")).get("states", {})
        except Exception:
            curation_states = {}

    cell = manifest.get("cell", {"width": 256, "height": 256})
    cw, ch = int(cell.get("width", 256)), int(cell.get("height", 256))
    rows_meta = manifest.get("animation", {}).get("rows", {})
    layout_rows = manifest.get("frame_layout", {}).get("rows", {})
    layout_frames = manifest.get("frame_layout", {}).get("frames", [])

    rects_by_state: dict[str, list[tuple[int, int, int, int]]] = {}
    for st, rlist in layout_rows.items():
        rects_by_state[st] = [
            (
                int(rf.get("x", 0)),
                int(rf.get("y", 0)),
                int(rf.get("w", rf.get("width", cw))),
                int(rf.get("h", rf.get("height", ch))),
            )
            for rf in rlist
        ]
    for lf in layout_frames:
        st = str(lf.get("state", "idle"))
        rects_by_state.setdefault(st, []).append(
            (
                int(lf.get("x", 0)),
                int(lf.get("y", 0)),
                int(lf.get("w", lf.get("width", cw))),
                int(lf.get("h", lf.get("height", ch))),
            )
        )

    runs_avail = [r["id"] for r in details.get("runs", [])]
    lines: list[str] = [
        f"PROJECT {project_id} {active_run} {','.join(runs_avail)}",
        f"INPUTS {active_input} {','.join(inputs_list)}",
        f"INPUT_PATH {inp_path}",
        f"DETECT {det_ok} {det_kind} {det_w} {det_h} {det_rows} {det_cols} {det_alpha} {det_chroma} {det_err}",
        f"DETECT_MSG {det_msg}",
        f"ATLAS {atlas_path}",
    ]

    for sname, rinfo in rows_meta.items():
        fps = float(rinfo.get("fps", 8.0))
        loop_flag = 1 if rinfo.get("loop", True) else 0
        st_ana = analysis.get("states", {}).get(sname, {})
        st_sum = st_ana.get("summary", {})
        status_str = st_sum.get("status", "NORMAL")
        hd_cnt = int(st_sum.get("head_drift_frames", 0))
        st_cnt = int(st_sum.get("stalled_frames", 0))
        jc_cnt = int(st_sum.get("jump_cut_frames", 0))
        bbox = st_ana.get("character_bbox", {"width": cw, "height": ch})
        lines.append(
            f"STATE {sname} {fps:.2f} {loop_flag} {status_str} {hd_cnt} {st_cnt} {jc_cnt} {bbox.get('width', cw)} {bbox.get('height', ch)}"
        )

        rects = rects_by_state.get(sname, [])
        ana_frames = st_ana.get("frames", [])
        st_transforms = curation_states.get(sname, {}).get("transforms", {})
        sel_counter = 0
        for f in ana_frames:
            idx = int(f["index"])
            sel = 1 if f.get("selected", True) else 0
            if sel and sel_counter < len(rects):
                rx, ry, rw, rh = rects[sel_counter]
                sel_counter += 1
            elif rects:
                rx, ry, rw, rh = rects[min(idx, len(rects) - 1)]
            else:
                rx, ry, rw, rh = 0, 0, cw, ch

            tr = st_transforms.get(str(idx), {})
            cur_dx = int(tr.get("dx", 0))
            cur_dy = int(tr.get("dy", 0))
            head_x = float(f.get("head_x", cw / 2))
            head_dx = float(f.get("head_dx_px", 0.0))
            head_pct = float(f.get("head_drift_pct", 0.0))
            r_leg = float(f.get("r_leg_pct", 0.0))
            leg_st = str(f.get("leg_status", "NORMAL"))
            head_st = str(f.get("head_status", "OK"))
            lines.append(
                f"FRAME {sname} {idx} {rx} {ry} {rw} {rh} {sel} {cur_dx} {cur_dy} {head_x:.2f} {head_dx:.2f} {head_pct:.2f} {r_leg:.2f} {head_st} {leg_st}"
            )

    meta_out = STUDIO_ROOT / "dxlib_meta.txt"
    meta_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return meta_out


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI bridge for AikaSpriteStudioDxLib.exe")
    parser.add_argument(
        "action",
        choices=[
            "sync",
            "import_file",
            "select_input",
            "cutout",
            "drop",
            "work",
            "slice_sheet",
            "ai_regen",
            "reroll_state",
            "inbetween",
            "seamless_bg",
            "stabilize",
            "reset",
            "nudge",
            "set_fps",
            "export",
        ],
    )
    parser.add_argument("--project", default="jirai-neko-demo")
    parser.add_argument("--run", default=None)
    parser.add_argument("--input", default=None)
    parser.add_argument("--state", default="walk")
    parser.add_argument("--states", default="idle,walk")
    parser.add_argument("--chroma", default="#00FF00")
    parser.add_argument("--breathe-mode", default="smooth")
    parser.add_argument("--frame", type=int, default=0)
    parser.add_argument("--dx", type=int, default=0)
    parser.add_argument("--dy", type=int, default=0)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--toggle", action="store_true")
    parser.add_argument("--file", default=None)
    parser.add_argument("--engine", default="all")
    args = parser.parse_args()

    ensure_default_demo_project()
    pdir = PROJECTS_DIR / args.project
    details = get_project_details(args.project)
    run_id = args.run or details.get("active_run") or "codex_run"

    if args.action == "sync":
        updates = {}
        if args.run:
            updates["active_run"] = args.run
        if args.input:
            updates["active_input"] = args.input
        if updates:
            update_project_meta(args.project, updates)
        write_dxlib_meta(args.project, args.run or run_id)
        return 0

    if args.action == "import_file" and args.file:
        src = Path(args.file)
        if src.exists():
            dest = pdir / "inputs" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            update_project_meta(args.project, {"active_input": src.name})
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "select_input" and args.input:
        update_project_meta(args.project, {"active_input": args.input})
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "cutout":
        inp_name = details.get("active_input") or "character_ref.jpg"
        src_path = pdir / "inputs" / inp_name
        if src_path.exists():
            out_name = f"{src_path.stem}_cutout.png"
            dst_path = pdir / "inputs" / out_name
            perform_auto_cutout(src_path, dst_path)
            update_project_meta(args.project, {"active_input": out_name})
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "drop" and args.file:
        src = Path(args.file)
        if src.exists():
            dest = pdir / "inputs" / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
            update_project_meta(args.project, {"active_input": src.name})
            args.action = "work"

    if args.action == "slice_sheet":
        details = get_project_details(args.project)
        inp_name = details.get("active_input") or "input_sheet.png"
        inp_path = pdir / "inputs" / inp_name
        new_run = f"slice_{inp_path.stem}"
        unpack_existing_sheet(inp_path, pdir / "runs" / new_run, args.states)
        update_project_meta(args.project, {"active_run": new_run})
        write_dxlib_meta(args.project, new_run)
        return 0

    if args.action in ("work", "ai_regen"):
        details = get_project_details(args.project)
        inp_name = details.get("active_input") or "input_sheet.png"
        inp_path = pdir / "inputs" / inp_name
        det = analyze_input_image(inp_path)
        if args.action == "work" and det.get("ok") and det.get("kind") == "sprite_sheet":
            new_run = f"slice_{inp_path.stem}"
            unpack_existing_sheet(inp_path, pdir / "runs" / new_run, args.states)
            update_project_meta(args.project, {"active_run": new_run})
            write_dxlib_meta(args.project, new_run)
        else:
            new_run = "codex_regen_run"
            base_img = inp_path if (inp_path.exists() and det.get("has_transparent_bg")) else (pdir / "inputs" / "base_chibi.png")
            if not base_img.exists():
                base_img = inp_path
            chroma = args.chroma if args.chroma != "auto" else det.get("recommended_chroma_key", "#00FF00")
            run_ai_sprite_pipeline(
                pdir / "runs" / new_run,
                args.project.replace("-", "_"),
                base_img,
                details.get("prompt") or "2D chibi anime game sprite facing right",
                chroma_key=chroma,
                states_spec=build_states_spec(args.states),
                provider="codex",
            )
            update_project_meta(args.project, {"active_run": new_run})
            write_dxlib_meta(args.project, new_run)
        return 0

    if args.action == "reroll_state":
        rdir = pdir / "runs" / run_id
        reroll_single_state(rdir, args.state)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "inbetween":
        rdir = pdir / "runs" / run_id
        interpolate_inbetween_frame(rdir, args.state, args.frame, args.frame + 1)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "seamless_bg":
        details = get_project_details(args.project)
        inp_name = details.get("active_input") or "input_sheet.png"
        inp_path = pdir / "inputs" / inp_name
        out_tile = STUDIO_ROOT / "seamless_stage_bg.png"
        make_seamless_background_tile(inp_path, out_tile)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "stabilize":
        rdir = pdir / "runs" / run_id
        apply_auto_stabilize(rdir, drop_stalled=True, enable_idle_breathe=True, breathe_mode=args.breathe_mode)
        recompose_run(rdir)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "reset":
        rdir = pdir / "runs" / run_id
        cpath = rdir / "curation.json"
        if cpath.exists():
            cpath.unlink()
            recompose_run(rdir)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "nudge":
        rdir = pdir / "runs" / run_id
        apply_manual_frame_edit(rdir, args.state, args.frame, args.dx, args.dy, args.toggle)
        recompose_run(rdir)
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "set_fps":
        rdir = pdir / "runs" / run_id
        mpath = rdir / "manifest.json"
        if mpath.exists():
            manifest = json.loads(mpath.read_text(encoding="utf-8"))
            rows = manifest.setdefault("animation", {}).setdefault("rows", {})
            if args.state in rows:
                rows[args.state]["fps"] = max(1.0, min(60.0, float(args.fps)))
                mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        write_dxlib_meta(args.project, run_id)
        return 0

    if args.action == "export":
        rdir = pdir / "runs" / run_id
        out_dir = pdir / "exported_code"
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.engine == "bundle":
            export_assets_bundle(rdir, out_dir / "asset_bundle")
        else:
            engines = ("dxlib", "html5", "phaser3", "godot4", "unity") if args.engine == "all" else (args.engine,)
            for eng in engines:
                res = export_code_by_engine(rdir, engine=eng, embed_base64=True)
                if res.get("ok"):
                    (out_dir / res["filename"]).write_text(res["code"], encoding="utf-8")
        write_dxlib_meta(args.project, run_id)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
