"""Automated tests for `app/exporters/template_codegen.py`, `ai_codegen.py`, and FastAPI routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import PROJECTS_DIR
from app.exporters.ai_codegen import generate_custom_sandbox_html
from app.exporters.template_codegen import export_code_by_engine
from app.main import app

CODEX_RUN = PROJECTS_DIR / "jirai-neko-demo" / "runs" / "codex_run"


def test_export_all_four_engines() -> None:
    for eng, expected_ext in [
        ("dxlib", ".cpp"),
        ("html5", ".html"),
        ("phaser3", ".js"),
        ("godot4", ".gd"),
        ("unity", ".cs"),
    ]:
        res = export_code_by_engine(CODEX_RUN, engine=eng, embed_base64=False, pixel_art=True)
        assert res["ok"] is True
        assert res["filename"].endswith(expected_ext)
        assert "jirai_neko" in res["code"]

    dx_res = export_code_by_engine(CODEX_RUN, engine="dxlib", embed_base64=False, pixel_art=True)
    assert '#include "DxLib.h"' in dx_res["code"]
    assert "DerivationGraph" in dx_res["code"]
    assert "DrawExtendGraph" in dx_res["code"]

    html_res = export_code_by_engine(CODEX_RUN, engine="html5", embed_base64=True, pixel_art=True)
    assert "ctx.imageSmoothingEnabled = !pixelMode;" in html_res["code"]
    assert "data:image/png;base64," in html_res["code"]


def test_ai_sandbox_codegen() -> None:
    res = generate_custom_sandbox_html(CODEX_RUN, custom_prompt="Double jump & Neko heart attack", pixel_art=False)
    assert res["ok"] is True
    assert "<canvas" in res["code"]
    assert "Double jump & Neko heart attack" in res["code"]


def test_fastapi_endpoints() -> None:
    client = TestClient(app)

    st = client.get("/api/status")
    assert st.status_code == 200
    assert st.json()["ok"] is True

    projs = client.get("/api/projects")
    assert projs.status_code == 200
    ids = [p["id"] for p in projs.json()["projects"]]
    assert "jirai-neko-demo" in ids

    code_resp = client.get("/api/projects/jirai-neko-demo/export-code?engine=html5&pixel_art=true")
    assert code_resp.status_code == 200
    assert code_resp.json()["ok"] is True


def test_codegen_rejects_unsupported_engine_and_malformed_manifests(tmp_path: Path) -> None:
    import json

    bad_eng = export_code_by_engine(CODEX_RUN, engine="unreal5")
    assert bad_eng["ok"] is False
    assert bad_eng["error_code"] == "UNSUPPORTED_ENGINE"

    missing_dir = tmp_path / "no_manifest_run"
    missing_dir.mkdir()
    missing_res = export_code_by_engine(missing_dir, engine="html5")
    assert missing_res["ok"] is False
    assert missing_res["error_code"] == "MANIFEST_NOT_FOUND"

    for payload in ("{not valid json", "[]", "{}", json.dumps({"animation": {"rows": {}}})):
        bad_dir = tmp_path / f"bad_{abs(hash(payload))}"
        bad_dir.mkdir(exist_ok=True)
        (bad_dir / "manifest.json").write_text(payload, encoding="utf-8")
        res = export_code_by_engine(bad_dir, engine="html5")
        assert res["ok"] is False
        assert res["error_code"] == "MANIFEST_INVALID"


def test_codegen_synthesizes_grid_rects_and_sanitizes_comments(tmp_path: Path) -> None:
    import json

    minimal_run = tmp_path / "minimal_run"
    minimal_run.mkdir()
    (minimal_run / "manifest.json").write_text(
        json.dumps(
            {
                "characterId": 'neko"hero<1>',
                "cell": {"width": 64, "height": 64},
                "animation": {
                    "rows": {
                        "idle": {"row": 0, "frames": 2, "fps": 5, "loop": True},
                        "walk": {"row": 1, "frames": 4, "fps": 8, "loop": True},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    for eng in ("dxlib", "html5", "phaser3", "godot4", "unity"):
        res = export_code_by_engine(minimal_run, engine=eng, embed_base64=False)
        assert res["ok"] is True
        assert "neko_hero_1" in res["code"]

    sandbox = generate_custom_sandbox_html(
        minimal_run,
        custom_prompt="Breakout --> <script>alert(1)</script>",
        pixel_art=True,
    )
    assert sandbox["ok"] is True
    # Ensure user prompt cannot prematurely close <!-- ... --> comment
    comment_line = next(line for line in sandbox["code"].splitlines() if "Custom Prompt:" in line)
    assert comment_line.count("-->") == 1
    assert "<script>alert(1)</script>" not in comment_line


def test_asset_exporter_bundle_and_stale_temp_cleanup(tmp_path: Path) -> None:
    import shutil
    from app.exporters.asset_exporter import export_assets_bundle

    run_copy = tmp_path / "run_copy"
    shutil.copytree(CODEX_RUN, run_copy)
    stale_frame = run_copy / "_forward_temp" / "frame-99.png"
    stale_frame.parent.mkdir(parents=True, exist_ok=True)
    stale_frame.write_bytes(b"stale")

    out_bundle = tmp_path / "bundle_out"
    res = export_assets_bundle(run_copy, out_bundle)
    assert res["ok"] is True
    assert not stale_frame.exists()
    assert (out_bundle / "sprite-sheet-alpha.png").is_file()
    assert (out_bundle / "manifest.json").is_file()
    assert (out_bundle / "previews" / "walk_forward_stage.gif").is_file()
    assert (out_bundle / "previews" / "walk_forward_transparent.gif").is_file()
