"""1-Click Auto-Stabilizer & Breathe Layer Configurator via `curation.json`.

Computes per-frame `dx`, `dy` offsets to lock head drift and pin feet to the baseline,
optionally drops stalled duplicate frames (`R_leg < 5.0%`), and bakes the result
through `sprite-gen compose-atlas` and `sprite-gen compose-gif`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from sprite_gen.curate import curation as sg_curation
except ImportError:  # sprite-gen is an external, read-only skill install (see ARCHITECTURE.md)
    sg_curation = None

from app.core.frame_analyzer import analyze_state_frames, list_frame_files


def _compute_state_revision(rdir: Path, state_name: str) -> str:
    """Return sprite-gen's state revision when available, or a deterministic SHA-256 fallback."""
    if sg_curation is not None and (rdir / "sprite-request.json").is_file():
        try:
            return sg_curation.state_revision(rdir, state_name)
        except (Exception, SystemExit):
            pass
    h = hashlib.sha256()
    sdir = rdir / "frames" / state_name
    for fp in list_frame_files(sdir):
        h.update(fp.name.encode("utf-8"))
        h.update(b"\x00")
        h.update(fp.read_bytes())
    return f"sha256:{h.hexdigest()[:16]}"


def _compute_run_revision(rdir: Path) -> str:
    """Return sprite-gen's run revision when available, or a deterministic SHA-256 fallback."""
    if sg_curation is not None and (rdir / "sprite-request.json").is_file():
        try:
            return sg_curation.run_revision(rdir)
        except (Exception, SystemExit):
            pass
    h = hashlib.sha256()
    frames_root = rdir / "frames"
    if frames_root.is_dir():
        for d in sorted(frames_root.iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                h.update(d.name.encode("utf-8"))
                h.update(b":")
                h.update(_compute_state_revision(rdir, d.name).encode("utf-8"))
                h.update(b"\n")
    return f"sha256:{h.hexdigest()[:16]}"


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
        if not isinstance(existing_states, dict):
            existing_states = {}

    run_rev = _compute_run_revision(rdir)
    new_states: dict[str, Any] = {}
    applied_changes: dict[str, Any] = {}

    for sdir in sorted(frames_root.iterdir()):
        if not sdir.is_dir() or sdir.name.startswith("_"):
            continue
        sname = sdir.name
        state_rev = _compute_state_revision(rdir, sname)

        # Analyze raw un-transformed frames first
        raw_analysis = analyze_state_frames(sdir, state_name=sname)
        if not raw_analysis.get("ok"):
            continue
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
        elif isinstance(existing_states.get(sname), dict) and "breathe" in existing_states[sname]:
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
    if not sdir.is_dir() or state_name.startswith("_"):
        return {"ok": False, "error": f"State '{state_name}' not found"}

    all_pngs = list_frame_files(sdir)
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
        if not isinstance(cdata, dict):
            cdata = {}

    run_rev = _compute_run_revision(rdir)
    states_map: dict[str, Any] = cdata.get("states", {})
    if not isinstance(states_map, dict):
        states_map = {}

    # Ensure every state in frames/ has a valid revision entry
    frames_root = rdir / "frames"
    for d in sorted(frames_root.iterdir()):
        if d.is_dir() and not d.name.startswith("_"):
            sn = d.name
            srev = _compute_state_revision(rdir, sn)
            if not isinstance(states_map.get(sn), dict):
                cnt = len(list_frame_files(d))
                states_map[sn] = {"revision": srev, "selected": list(range(cnt))}
            else:
                states_map[sn]["revision"] = srev

    st_entry = states_map[state_name]
    raw_selected = st_entry.get("selected", list(range(total_frames)))
    if isinstance(raw_selected, list) and all(isinstance(i, int) and not isinstance(i, bool) for i in raw_selected):
        selected: list[int] = sorted({i for i in raw_selected if 0 <= i < total_frames})
        if not selected:
            selected = list(range(total_frames))
    else:
        selected = list(range(total_frames))
    raw_transforms = st_entry.get("transforms", {})
    transforms: dict[str, dict[str, Any]] = dict(raw_transforms) if isinstance(raw_transforms, dict) else {}

    if toggle_selected:
        if frame_index in selected:
            if len(selected) > 1:
                selected.remove(frame_index)
        else:
            selected.append(frame_index)
            selected.sort()
        st_entry["selected"] = selected

    if delta_dx != 0 or delta_dy != 0:
        prev_tr = transforms.get(str(frame_index))
        cur_tr = dict(prev_tr) if isinstance(prev_tr, dict) else {"dx": 0, "dy": 0}
        try:
            base_dx = int(round(float(cur_tr.get("dx", 0))))
        except (TypeError, ValueError, OverflowError):
            base_dx = 0
        try:
            base_dy = int(round(float(cur_tr.get("dy", 0))))
        except (TypeError, ValueError, OverflowError):
            base_dy = 0
        cur_tr["dx"] = base_dx + delta_dx
        cur_tr["dy"] = base_dy + delta_dy
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

