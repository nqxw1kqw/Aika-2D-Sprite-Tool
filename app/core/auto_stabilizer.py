"""1-Click Auto-Stabilizer & Breathe Layer Configurator via `curation.json`.

Computes per-frame `dx`, `dy` offsets to lock head drift and pin feet to the baseline,
optionally drops stalled duplicate frames (`R_leg < 5.0%`), and bakes the result
through `sprite-gen compose-atlas` and `sprite-gen compose-gif`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sprite_gen.curate import curation as sg_curation

from app.core.frame_analyzer import analyze_state_frames


def apply_auto_stabilize(
    run_dir: str | Path,
    drop_stalled: bool = True,
    enable_idle_breathe: bool = True,
    breathe_mode: str = "smooth",
    custom_state_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate or update curation.json in run_dir to stabilize head/ground and filter stalled frames."""
    rdir = Path(run_dir)
    frames_root = rdir / "frames"
    if not frames_root.exists():
        return {"ok": False, "error": f"Missing frames directory in {rdir}"}

    curation_path = rdir / "curation.json"
    existing_states: dict[str, Any] = {}
    if curation_path.exists():
        try:
            existing_states = json.loads(curation_path.read_text(encoding="utf-8")).get("states", {})
        except Exception:
            existing_states = {}

    run_rev = sg_curation.run_revision(rdir)
    new_states: dict[str, Any] = {}
    applied_changes: dict[str, Any] = {}

    for sdir in sorted(frames_root.iterdir()):
        if not sdir.is_dir() or sdir.name.startswith("_"):
            continue
        sname = sdir.name
        state_rev = sg_curation.state_revision(rdir, sname)

        # Analyze raw un-transformed frames first
        raw_analysis = analyze_state_frames(sdir, state_name=sname)
        frames_info = raw_analysis.get("frames", [])
        is_loco = bool(raw_analysis.get("is_locomotion", False))

        selected: list[int] = []
        transforms: dict[str, dict[str, int]] = {}
        dropped_frames: list[int] = []

        for f in frames_info:
            idx = int(f["index"])
            dx = int(f["recommended_dx"])
            dy = int(f["recommended_dy"])
            if dx != 0 or dy != 0:
                transforms[str(idx)] = {"dx": dx, "dy": dy}

            # If frame is STALLED in a locomotion cycle (meaning idx -> next_idx has R_leg < 5%),
            # dropping the duplicate next_idx removes the pause while keeping at least 3 frames.
            if drop_stalled and is_loco and f["leg_status"] == "STALLED" and len(frames_info) - len(dropped_frames) > 3:
                dup_idx = int(f["next_frame_index"])
                if dup_idx != 0 and dup_idx not in dropped_frames:
                    dropped_frames.append(dup_idx)

        for f in frames_info:
            idx = int(f["index"])
            if idx not in dropped_frames:
                selected.append(idx)

        state_entry: dict[str, Any] = {
            "revision": state_rev,
            "selected": selected,
        }
        if transforms:
            state_entry["transforms"] = transforms

        # Preserve or apply breathe on idle state
        if sname == "idle" and enable_idle_breathe:
            state_entry["breathe"] = {
                "mode": breathe_mode if breathe_mode in ("pixel", "smooth") else "smooth",
                "depth": 0.02,
                "depth_x": 0.03,
            }
        elif "breathe" in existing_states.get(sname, {}):
            state_entry["breathe"] = existing_states[sname]["breathe"]

        if custom_state_overrides and sname in custom_state_overrides:
            state_entry.update(custom_state_overrides[sname])

        new_states[sname] = state_entry
        applied_changes[sname] = {
            "selected": selected,
            "dropped_stalled_frames": dropped_frames,
            "transforms": transforms,
            "breathe": state_entry.get("breathe"),
        }

    curation_payload = {
        "version": 1,
        "kind": "sprite-gen-curation",
        "run_revision": run_rev,
        "states": new_states,
    }
    curation_path.write_text(json.dumps(curation_payload, indent=2), encoding="utf-8")

    return {
        "ok": True,
        "curation_path": str(curation_path),
        "run_revision": run_rev,
        "changes": applied_changes,
    }


def apply_manual_frame_edit(
    run_dir: str | Path,
    state_name: str,
    frame_index: int,
    delta_dx: int = 0,
    delta_dy: int = 0,
    toggle_selected: bool = False,
) -> dict[str, Any]:
    """Adjust a single frame's dx, dy or selected state in curation.json."""
    rdir = Path(run_dir)
    sdir = rdir / "frames" / state_name
    if not sdir.exists():
        return {"ok": False, "error": f"State '{state_name}' not found"}

    all_pngs = sorted(sdir.glob("frame-*.png"), key=lambda p: int(p.stem.split("-")[1]))
    total_frames = len(all_pngs)
    if not (0 <= frame_index < total_frames):
        return {"ok": False, "error": f"Invalid frame index {frame_index}"}

    curation_path = rdir / "curation.json"
    cdata: dict[str, Any] = {}
    if curation_path.exists():
        try:
            cdata = json.loads(curation_path.read_text(encoding="utf-8"))
        except Exception:
            cdata = {}

    run_rev = sg_curation.run_revision(rdir)
    states_map: dict[str, Any] = cdata.get("states", {})

    # Ensure every state in frames/ has a valid revision entry
    frames_root = rdir / "frames"
    for d in sorted(frames_root.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            sn = d.name
            srev = sg_curation.state_revision(rdir, sn)
            if sn not in states_map:
                cnt = len(list(d.glob("frame-*.png")))
                states_map[sn] = {"revision": srev, "selected": list(range(cnt))}
            else:
                states_map[sn]["revision"] = srev

    st_entry = states_map[state_name]
    selected: list[int] = list(st_entry.get("selected", list(range(total_frames))))
    transforms: dict[str, dict[str, Any]] = dict(st_entry.get("transforms", {}))

    if toggle_selected:
        if frame_index in selected:
            if len(selected) > 1:
                selected.remove(frame_index)
        else:
            selected.append(frame_index)
            selected.sort()
        st_entry["selected"] = selected

    if delta_dx != 0 or delta_dy != 0:
        cur_tr = dict(transforms.get(str(frame_index), {"dx": 0, "dy": 0}))
        cur_tr["dx"] = int(cur_tr.get("dx", 0)) + delta_dx
        cur_tr["dy"] = int(cur_tr.get("dy", 0)) + delta_dy
        if cur_tr["dx"] == 0 and cur_tr["dy"] == 0:
            transforms.pop(str(frame_index), None)
        else:
            transforms[str(frame_index)] = cur_tr
        if transforms:
            st_entry["transforms"] = transforms
        else:
            st_entry.pop("transforms", None)

    payload = {
        "version": 1,
        "kind": "sprite-gen-curation",
        "run_revision": run_rev,
        "states": states_map,
    }
    curation_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"ok": True, "state": state_name, "frame_index": frame_index, "entry": st_entry}

