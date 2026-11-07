"""Normalized Frame-by-Frame Analyzer (v2.0).

Implements resolution-independent metrics for any 2D sprite or pixel art run:
1. Hair-Resistant Head Anchor (`Head Drift` in px and % of character width):
   Uses `sprite_gen.effects.breathe.analyze` for anatomy + Leading Face Contour
   in the upper face band `[top + 0.12*H .. top + 0.38*H]` so swinging twintails
   or capes behind the head do not cause false-positive head wobble.
2. Baseline Drift (`abs(y_bottom(i) - baseline_y)` in px).
3. Normalized Leg Motion Ratio (`R_leg` in %, continuous closed intervals):
   - `STALLED` (< 5.0%): Duplicate or near-frozen leg pose
   - `NORMAL` (5.0% <= R_leg <= 35.0%): Smooth even step progression
   - `JUMP_CUT` (> 35.0%): Abrupt pose jump needing AI in-between interpolation
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    from sprite_gen.effects import breathe as sg_breathe
except ImportError:
    sg_breathe = None


def _measure_leading_face_x(arr: np.ndarray, top0: int, char_h: float, facing: str = "right") -> float:
    """Measure leading face contour X in the upper face band, ignoring back hair."""
    hy0 = max(0, int(top0 + 0.12 * char_h))
    hy1 = min(arr.shape[0], max(hy0 + 4, int(top0 + 0.38 * char_h)))
    band = arr[hy0:hy1, :, 3] > 128
    edges: list[int] = []
    for r in range(band.shape[0]):
        xs = np.where(band[r])[0]
        if xs.size > 0:
            edges.append(int(xs.max()) if facing != "left" else int(xs.min()))
    if not edges:
        ys, xs = np.where(arr[:, :, 3] > 64)
        return float(np.mean(xs)) if xs.size > 0 else 0.0
    return float(np.median(edges))


def analyze_state_frames(
    frames_dir: str | Path,
    state_name: str = "walk",
    facing: str = "right",
    transforms: dict[str, dict[str, Any]] | None = None,
    selected_indices: list[int] | None = None,
) -> dict[str, Any]:
    """Analyze all frame-*.png files in a state directory and return per-frame & summary metrics."""
    fdir = Path(frames_dir)
    all_files = sorted(fdir.glob("frame-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    if not all_files:
        return {
            "ok": False,
            "state": state_name,
            "frame_count": 0,
            "frames": [],
            "summary": {"status": "EMPTY", "issues_count": 0},
        }

    transforms = transforms or {}
    if selected_indices is not None:
        active_indices = [idx for idx in selected_indices if 0 <= idx < len(all_files)]
    else:
        active_indices = list(range(len(all_files)))

    if not active_indices:
        active_indices = list(range(len(all_files)))

    # Load RGBA arrays and apply any active curation transforms (dx, dy)
    raw_arrays: dict[int, np.ndarray] = {}
    first_im: Image.Image | None = None
    for idx, fp in enumerate(all_files):
        with Image.open(fp) as im:
            rgba = im.convert("RGBA")
            if first_im is None:
                first_im = rgba.copy()
            arr = np.array(rgba, dtype=float)
            tr = transforms.get(str(idx), {})
            dx = int(round(float(tr.get("dx", 0))))
            dy = int(round(float(tr.get("dy", 0))))
            if dx != 0 or dy != 0:
                shifted = np.zeros_like(arr)
                h, w = arr.shape[:2]
                src_x0 = max(0, -dx)
                src_x1 = min(w, w - dx)
                dst_x0 = max(0, dx)
                dst_x1 = min(w, w + dx)
                src_y0 = max(0, -dy)
                src_y1 = min(h, h - dy)
                dst_y0 = max(0, dy)
                dst_y1 = min(h, h + dy)
                if src_x1 > src_x0 and src_y1 > src_y0:
                    shifted[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
                arr = shifted
            raw_arrays[idx] = arr

    ref_idx = active_indices[0]
    ref_arr = raw_arrays[ref_idx]
    cell_h, cell_w = ref_arr.shape[:2]

    ys0, xs0 = np.where(ref_arr[:, :, 3] > 64)
    if ys0.size == 0:
        top0, bot0, x0, x1 = 0, cell_h - 1, 0, cell_w - 1
    else:
        top0, bot0 = int(ys0.min()), int(ys0.max())
        x0, x1 = int(xs0.min()), int(xs0.max())

    char_w = float(max(1, x1 - x0 + 1))
    char_h = float(max(1, bot0 - top0 + 1))

    anatomy_info: dict[str, Any] = {}
    if sg_breathe is not None and first_im is not None:
        try:
            anat = sg_breathe.analyze(first_im)
            anatomy_info = {
                "neck_row": int(anat.neck_row),
                "axis_x": int(anat.axis_x),
                "width": int(anat.width),
                "height": int(anat.height),
            }
        except Exception:
            anatomy_info = {}

    # Compute per-frame head anchor and baseline
    head_xs: dict[int, float] = {}
    bottom_ys: dict[int, int] = {}
    for idx in range(len(all_files)):
        arr = raw_arrays[idx]
        head_xs[idx] = _measure_leading_face_x(arr, top0, char_h, facing=facing)
        ys, _ = np.where(arr[:, :, 3] > 16)
        bottom_ys[idx] = int(ys.max()) if ys.size > 0 else bot0

    ref_head_x = head_xs[ref_idx]
    baseline_y = int(np.median([bottom_ys[i] for i in active_indices]))

    # Compute leg ROI [top0 + 0.70*char_h .. bot0]
    leg_y0 = max(0, int(top0 + 0.70 * char_h))
    leg_y1 = min(cell_h, bot0 + 1)
    is_locomotion = any(k in state_name.lower() for k in ("walk", "run", "move", "dash"))

    frames_report: list[dict[str, Any]] = []
    head_drift_count = 0
    stalled_count = 0
    jump_cut_count = 0
    baseline_drift_count = 0

    for idx in range(len(all_files)):
        is_selected = idx in active_indices
        dx_px = head_xs[idx] - ref_head_x
        drift_pct = (abs(dx_px) / char_w) * 100.0
        # Good if drift_pct <= 1.5% OR abs(dx_px) <= 1.0 px
        head_ok = (drift_pct <= 1.5) or (abs(dx_px) <= 1.0)
        recommended_dx = int(round(-dx_px)) if not head_ok else 0

        dy_ground = bottom_ys[idx] - baseline_y
        ground_ok = abs(dy_ground) <= 1
        recommended_dy = int(-dy_ground) if not ground_ok else 0

        # Leg motion ratio to next active frame
        if is_selected and len(active_indices) > 1:
            pos = active_indices.index(idx)
            next_idx = active_indices[(pos + 1) % len(active_indices)]
        else:
            next_idx = (idx + 1) % len(all_files)

        box_i = raw_arrays[idx][leg_y0:leg_y1, x0 : x1 + 1, :]
        box_j = raw_arrays[next_idx][leg_y0:leg_y1, x0 : x1 + 1, :]
        raw_leg_delta = float(np.abs(box_i - box_j).mean()) if box_i.size > 0 else 0.0
        if is_locomotion:
            r_leg = max(0.0, (raw_leg_delta / 108.0) * 100.0 - 5.2)
        else:
            r_leg = (raw_leg_delta / 108.0) * 100.0

        # Continuous closed classification: < 5.0% STALLED, 5.0%..35.0% NORMAL, > 35.0% JUMP_CUT
        if not is_locomotion:
            leg_status = "NORMAL"
        elif r_leg < 5.0:
            leg_status = "STALLED"
        elif r_leg <= 35.0:
            leg_status = "NORMAL"
        else:
            leg_status = "JUMP_CUT"

        if is_selected:
            if not head_ok:
                head_drift_count += 1
            if not ground_ok:
                baseline_drift_count += 1
            if is_locomotion and leg_status == "STALLED":
                stalled_count += 1
            elif is_locomotion and leg_status == "JUMP_CUT":
                jump_cut_count += 1

        frame_badges: list[str] = []
        if not is_selected:
            frame_badges.append("SKIPPED")
        else:
            if not head_ok:
                frame_badges.append("HEAD_DRIFT")
            if not ground_ok:
                frame_badges.append("BASELINE_DRIFT")
            if is_locomotion and leg_status != "NORMAL":
                frame_badges.append(leg_status)
            if not frame_badges:
                frame_badges.append("OK")

        frames_report.append(
            {
                "index": idx,
                "file": all_files[idx].name,
                "selected": is_selected,
                "head_x": round(head_xs[idx], 2),
                "head_dx_px": round(dx_px, 2),
                "head_drift_pct": round(drift_pct, 2),
                "head_status": "OK" if head_ok else "HEAD_DRIFT",
                "recommended_dx": recommended_dx,
                "bottom_y": bottom_ys[idx],
                "baseline_dy_px": dy_ground,
                "ground_status": "OK" if ground_ok else "BASELINE_DRIFT",
                "recommended_dy": recommended_dy,
                "next_frame_index": next_idx,
                "r_leg_pct": round(r_leg, 2),
                "leg_status": leg_status,
                "badges": frame_badges,
            }
        )

    total_issues = head_drift_count + stalled_count + jump_cut_count + baseline_drift_count
    overall_status = "NORMAL" if total_issues == 0 else "NEEDS_STABILIZATION"

    return {
        "ok": True,
        "state": state_name,
        "is_locomotion": is_locomotion,
        "cell_size": [cell_w, cell_h],
        "character_bbox": {"width": int(char_w), "height": int(char_h), "baseline_y": baseline_y},
        "anatomy": anatomy_info,
        "frame_count": len(all_files),
        "selected_count": len(active_indices),
        "frames": frames_report,
        "summary": {
            "status": overall_status,
            "issues_count": total_issues,
            "head_drift_frames": head_drift_count,
            "baseline_drift_frames": baseline_drift_count,
            "stalled_frames": stalled_count,
            "jump_cut_frames": jump_cut_count,
            "can_auto_stabilize": (head_drift_count > 0 or baseline_drift_count > 0 or stalled_count > 0),
        },
    }


def analyze_run_directory(run_dir: str | Path) -> dict[str, Any]:
    """Analyze all states in a sprite-gen run directory, honoring curation.json if present."""
    rdir = Path(run_dir)
    frames_root = rdir / "frames"
    if not frames_root.exists():
        return {"ok": False, "error": f"No frames directory in {rdir}"}

    curation_path = rdir / "curation.json"
    curation_states: dict[str, Any] = {}
    if curation_path.exists():
        try:
            cdata = json.loads(curation_path.read_text(encoding="utf-8"))
            curation_states = cdata.get("states", {})
        except Exception:
            curation_states = {}

    states_report: dict[str, Any] = {}
    for sdir in sorted(frames_root.iterdir()):
        if sdir.is_dir() and not sdir.name.startswith("_"):
            sname = sdir.name
            scur = curation_states.get(sname, {})
            states_report[sname] = analyze_state_frames(
                sdir,
                state_name=sname,
                transforms=scur.get("transforms"),
                selected_indices=scur.get("selected"),
            )

    return {
        "ok": True,
        "run_dir": str(rdir),
        "has_curation": curation_path.exists(),
        "states": states_report,
    }
