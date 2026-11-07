"""Automated tests for `app/core/frame_analyzer.py` and `app/core/auto_stabilizer.py`."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import PROJECTS_DIR
from app.core.auto_stabilizer import apply_auto_stabilize, apply_manual_frame_edit
from app.core.frame_analyzer import analyze_run_directory, analyze_state_frames
from app.core.pipeline_runner import build_states_spec, make_seamless_background_tile

DEMO_RUNS = PROJECTS_DIR / "jirai-neko-demo" / "runs"


def test_unpacked_run_detects_head_drift_and_uneven_legs() -> None:
    walk_dir = DEMO_RUNS / "unpacked_run" / "frames" / "walk"
    res = analyze_state_frames(walk_dir, state_name="walk")
    assert res["ok"] is True
    assert res["frame_count"] == 8
    summary = res["summary"]
    assert summary["status"] == "NEEDS_STABILIZATION"
    assert summary["head_drift_frames"] >= 3
    assert summary["stalled_frames"] >= 1
    assert summary["jump_cut_frames"] >= 1
    assert summary["can_auto_stabilize"] is True


def test_codex_run_passes_all_normalized_checks() -> None:
    walk_dir = DEMO_RUNS / "codex_run" / "frames" / "walk"
    res = analyze_state_frames(walk_dir, state_name="walk")
    assert res["ok"] is True
    assert res["frame_count"] == 6
    summary = res["summary"]
    assert summary["status"] == "NORMAL"
    assert summary["head_drift_frames"] == 0
    assert summary["stalled_frames"] == 0
    assert summary["jump_cut_frames"] == 0


def test_auto_stabilizer_fixes_head_drift_and_stalled_frames(tmp_path: Path) -> None:
    temp_run = tmp_path / "unpacked_copy"
    shutil.copytree(DEMO_RUNS / "unpacked_run", temp_run)

    stab = apply_auto_stabilize(temp_run, drop_stalled=True, enable_idle_breathe=True)
    assert stab["ok"] is True
    assert (temp_run / "curation.json").exists()

    after = analyze_run_directory(temp_run)
    walk_after = after["states"]["walk"]
    assert walk_after["summary"]["head_drift_frames"] == 0
    assert walk_after["summary"]["stalled_frames"] == 0
    assert walk_after["selected_count"] == 7


def test_manual_frame_edit_and_states_spec(tmp_path: Path) -> None:
    temp_run = tmp_path / "codex_copy"
    shutil.copytree(DEMO_RUNS / "codex_run", temp_run)

    edit_res = apply_manual_frame_edit(temp_run, "walk", frame_index=2, delta_dx=3, delta_dy=-1, toggle_selected=True)
    assert edit_res["ok"] is True
    assert 2 not in edit_res["entry"]["selected"]
    assert edit_res["entry"]["transforms"]["2"] == {"dx": 3, "dy": -1}

    spec = build_states_spec("idle,walk,run,jump,attack")
    assert set(spec.keys()) == {"idle", "walk", "run", "jump", "attack"}
    assert spec["jump"]["loop"] is False


def test_seamless_background_tile(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    src_bg = tmp_path / "sample_bg.png"
    im = Image.new("RGBA", (600, 240), (30, 25, 45, 255))
    draw = ImageDraw.Draw(im)
    for x in range(0, 600, 40):
        draw.rectangle([x, 160, x + 20, 240], fill=(70, 50, 95, 255))
    im.save(src_bg)

    out_tile = tmp_path / "tiled_bg.png"
    res = make_seamless_background_tile(src_bg, out_tile, period=512, overlap=32)
    assert res["ok"] is True
    assert out_tile.exists()
    with Image.open(out_tile) as tiled_im:
        assert tiled_im.size == (512, 240)

    bad_params = make_seamless_background_tile(src_bg, tmp_path / "bad.png", period=32, overlap=32)
    assert bad_params["ok"] is False
    assert bad_params["error_code"] == "INVALID_PARAMS"


def test_list_frame_files_numeric_order_and_ignores_junk(tmp_path: Path) -> None:
    from PIL import Image
    from app.core.frame_analyzer import list_frame_files

    sdir = tmp_path / "walk"
    sdir.mkdir()
    for name in ("frame-10.png", "frame-2.png", "frame-0.png", "frame-old.png", "notes.txt"):
        if name.endswith(".png"):
            Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(sdir / name)
        else:
            (sdir / name).write_text("ignore", encoding="utf-8")

    ordered = [p.name for p in list_frame_files(sdir)]
    assert ordered == ["frame-0.png", "frame-2.png", "frame-10.png"]
    assert list_frame_files(tmp_path / "missing") == []


def test_analyzer_and_manual_edit_resilience_to_bad_curation_and_sizes(tmp_path: Path) -> None:
    from PIL import Image, ImageDraw

    run_dir = tmp_path / "custom_run"
    walk_dir = run_dir / "frames" / "walk"
    walk_dir.mkdir(parents=True)

    # Frame 0 is 64x64, Frame 1 is 48x56 (mismatched canvas size)
    f0 = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(f0).rectangle([20, 12, 42, 58], fill=(240, 100, 160, 255))
    f0.save(walk_dir / "frame-0.png")

    f1 = Image.new("RGBA", (48, 56), (0, 0, 0, 0))
    ImageDraw.Draw(f1).rectangle([18, 12, 38, 54], fill=(240, 100, 160, 255))
    f1.save(walk_dir / "frame-1.png")

    # Malformed curation.json with bad transform values and out-of-range selected indices
    (run_dir / "curation.json").write_text(
        '{"states": {"walk": {"selected": [0], "transforms": {"0": {"dx": "bad", "dy": null}}}}}',
        encoding="utf-8",
    )

    report = analyze_run_directory(run_dir)
    assert report["ok"] is True
    assert report["states"]["walk"]["ok"] is True

    # Cannot deselect the sole remaining active frame (index 0)
    keep_res = apply_manual_frame_edit(run_dir, "walk", frame_index=0, delta_dx=2, toggle_selected=True)
    assert keep_res["ok"] is True
    assert keep_res["entry"]["selected"] == [0]
    assert keep_res["entry"]["transforms"]["0"] == {"dx": 2, "dy": 0}

    # Corrupt frame file returns ok=False instead of raising
    (walk_dir / "frame-2.png").write_bytes(b"corrupt-png")
    corrupt_state = analyze_state_frames(walk_dir, state_name="walk")
    assert corrupt_state["ok"] is False
    assert corrupt_state["summary"]["status"] == "CORRUPT_FRAME"

