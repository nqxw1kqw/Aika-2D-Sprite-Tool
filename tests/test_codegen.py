"""Automated tests for `app/exporters/template_codegen.py`, `ai_codegen.py`, and FastAPI routes."""

from __future__ import annotations

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
