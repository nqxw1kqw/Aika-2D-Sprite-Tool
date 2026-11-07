"""Automated tests for `app/core/detector.py` using the `jirai-neko-demo` fixture."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.config import PROJECTS_DIR
from app.core.detector import analyze_input_image

DEMO_INPUTS = PROJECTS_DIR / "jirai-neko-demo" / "inputs"


def test_detect_multi_frame_sprite_sheet() -> None:
    sheet_path = DEMO_INPUTS / "input_sheet.png"
    res = analyze_input_image(sheet_path)
    assert res["ok"] is True
    assert res["kind"] == "sprite_sheet"
    assert res["estimated_rows"] == 2
    assert res["estimated_frames"] >= 12
    assert res["has_transparent_bg"] is True


def test_detect_single_still_character() -> None:
    still_path = DEMO_INPUTS / "base_chibi.png"
    res = analyze_input_image(still_path)
    assert res["ok"] is True
    assert res["kind"] == "single_still"
    assert res["estimated_frames"] == 1
    assert res["recommended_chroma_key"] == "#00FF00"


def test_detect_opaque_reference_triggers_error_gate() -> None:
    ref_path = DEMO_INPUTS / "character_ref.jpg"
    res = analyze_input_image(ref_path)
    assert res["ok"] is False
    assert res["kind"] == "invalid"
    assert res["error_code"] == "OPAQUE_WALL"
    assert res["suggest_cutout"] is True


def test_detect_empty_transparent_image(tmp_path: Path) -> None:
    empty_png = tmp_path / "empty.png"
    Image.new("RGBA", (128, 128), (0, 0, 0, 0)).save(empty_png)
    res = analyze_input_image(empty_png)
    assert res["ok"] is False
    assert res["error_code"] == "EMPTY_ALPHA"
