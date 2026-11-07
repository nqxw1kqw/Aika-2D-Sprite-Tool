"""Focused tests for Project Manager, Pipeline Exit 75/error handling, Bridges, and FastAPI validation."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import app.bridges.skill_registry as skill_registry
import app.core.pipeline_runner as pipeline_runner
import app.dxlib_cli_bridge as dxlib_cli_bridge
import app.main as main_mod
import app.project_manager as pm_mod
from app.config import PROJECTS_DIR as REAL_PROJECTS_DIR


@pytest.fixture()
def isolated_projects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect PROJECTS_DIR to an isolated temporary directory seeded with demo runs."""
    pdir = tmp_path / "projects"
    pdir.mkdir()
    monkeypatch.setattr(pm_mod, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(main_mod, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(dxlib_cli_bridge, "PROJECTS_DIR", pdir)
    monkeypatch.setattr(dxlib_cli_bridge, "STUDIO_ROOT", tmp_path)
    return pdir


def _make_rgba_bytes(size: tuple[int, int] = (64, 64), bg: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bytes:
    im = Image.new("RGBA", size, bg)
    draw = ImageDraw.Draw(im)
    draw.rectangle([16, 12, size[0] - 16, size[1] - 10], fill=(236, 72, 153, 255))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def test_project_manager_slug_collisions_unicode_and_corrupt_files(isolated_projects: Path) -> None:
    p1 = pm_mod.create_project("Hero Sprite")
    p2 = pm_mod.create_project("Hero Sprite")
    p3 = pm_mod.create_project("地雷系ネコ")
    assert p1["id"] == "hero-sprite"
    assert p2["id"] == "hero-sprite-2"
    assert p3["name"] == "地雷系ネコ"

    # Corrupt project.json and non-string active_run must not crash get_project_details
    pjson = isolated_projects / "hero-sprite" / "project.json"
    pjson.write_text("{corrupt", encoding="utf-8")
    assert pm_mod.get_project_details("hero-sprite")["ok"] is True

    pjson.write_text(json.dumps({"id": "hero-sprite", "active_run": 999, "active_input": ["bad"]}), encoding="utf-8")
    details = pm_mod.get_project_details("hero-sprite")
    assert details["ok"] is True
    assert details["active_run"] is None
    assert details["active_input"] is None

    # A corrupt manifest.json in one run must not crash project listing
    bad_run = isolated_projects / "hero-sprite" / "runs" / "broken_run"
    bad_run.mkdir(parents=True)
    (bad_run / "manifest.json").write_text("{broken-json", encoding="utf-8")
    listed = pm_mod.list_projects()
    hero_loaded = next(p for p in listed if p["id"] == "hero-sprite")
    assert hero_loaded["run_detail"]["ok"] is False

    # Reject path traversal segments
    assert pm_mod.get_project_details("../outside")["ok"] is False
    assert pm_mod.get_run_details("hero-sprite", "../outside")["ok"] is False
    with pytest.raises(ValueError):
        pm_mod.update_project_meta("../outside", {"prompt": "nope"})
    with pytest.raises(FileNotFoundError):
        pm_mod.update_project_meta("missing-project", {"prompt": "nope"})


def test_pipeline_runner_exit_75_timeout_and_missing_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 1. Exit 75 codex-unavailable with structured ask payload
    def fake_exit_75(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["sprite-gen"],
            returncode=75,
            stdout="",
            stderr='sprite-gen ask codex-unavailable: {"cause": "quota_exceeded", "provider": "codex"}',
        )

    monkeypatch.setattr(subprocess, "run", fake_exit_75)
    res_75 = pipeline_runner.run_sprite_gen_cmd(["gen-set", "--run-dir", str(tmp_path)])
    assert res_75["ok"] is False
    assert res_75["exit_code"] == 75
    assert res_75["error_code"] == "CODEX_UNAVAILABLE"
    assert res_75["ask"] == {"cause": "quota_exceeded", "provider": "codex"}

    interp_75 = pipeline_runner.interpolate_inbetween_frame(tmp_path, "walk", 0, 1)
    assert interp_75["exit_code"] == 75
    assert interp_75["error_code"] == "CODEX_UNAVAILABLE"

    # 2. Subprocess timeout -> TIMEOUT
    def fake_timeout(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="sprite-gen", timeout=5)

    monkeypatch.setattr(subprocess, "run", fake_timeout)
    res_to = pipeline_runner.run_sprite_gen_cmd(["inspect"], timeout=5)
    assert res_to["ok"] is False
    assert res_to["error_code"] == "TIMEOUT"

    # 3. Missing executable -> SPRITE_GEN_MISSING
    def fake_missing(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("sprite-gen not found")

    monkeypatch.setattr(subprocess, "run", fake_missing)
    res_miss = pipeline_runner.run_sprite_gen_cmd(["inspect"])
    assert res_miss["ok"] is False
    assert res_miss["error_code"] == "SPRITE_GEN_MISSING"


def test_skill_registry_and_dxlib_meta_bridge(
    isolated_projects: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Skill registry frontmatter & featured sorting
    codex_dir = tmp_path / "codex_skills"
    (codex_dir / "custom-tool").mkdir(parents=True)
    (codex_dir / "custom-tool" / "SKILL.md").write_text(
        "---\nname: Custom Tool\ndescription: Helper\n---\n# Custom\nBody",
        encoding="utf-8",
    )
    (codex_dir / "sprite-gen").mkdir(parents=True)
    (codex_dir / "sprite-gen" / "LICENSE.txt").write_text("Apache-2.0", encoding="utf-8")
    (codex_dir / "sprite-gen" / "SKILL.md").write_text(
        '---\nname: "sprite-gen"\nversion: "4.0.0"\ndescription: "2D Sprite Pipeline"\n---\n# Sprite Gen\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(skill_registry, "CODEX_SKILLS_DIR", codex_dir)
    monkeypatch.setattr(skill_registry, "GEMINI_SKILLS_DIR", tmp_path / "empty_gemini")

    skills = skill_registry.list_installed_skills()
    assert [s["id"] for s in skills] == ["sprite-gen", "custom-tool"]
    assert skills[0]["is_featured_2d"] is True
    assert skills[0]["license"] == "Apache-2.0"
    assert skill_registry.read_skill_preview("sprite-gen", max_chars=20)["truncated"] is True
    assert skill_registry.read_skill_preview("missing")["ok"] is False

    # DxLib meta bridge accurately records multi-row sprite_sheet detection
    demo_dst = isolated_projects / "jirai-neko-demo"
    shutil.copytree(REAL_PROJECTS_DIR / "jirai-neko-demo" / "inputs", demo_dst / "inputs")
    shutil.copytree(
        REAL_PROJECTS_DIR / "jirai-neko-demo" / "runs" / "codex_run",
        demo_dst / "runs" / "codex_run",
    )
    meta_file = dxlib_cli_bridge.write_dxlib_meta("jirai-neko-demo", "codex_run")
    lines = meta_file.read_text(encoding="utf-8").splitlines()
    detect_line = next(line for line in lines if line.startswith("DETECT "))
    # DETECT <ok> <kind> <w> <h> <rows> <cols> ...
    parts = detect_line.split()
    assert parts[1] == "1"
    assert parts[2] == "sprite_sheet"
    assert int(parts[5]) == 2
    assert int(parts[6]) >= 6


def test_fastapi_validation_uploads_manifests_and_exit_75(
    isolated_projects: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed isolated demo project with unpacked_run so stabilize/frame-edit/export can be tested safely
    demo_dst = isolated_projects / "jirai-neko-demo"
    shutil.copytree(REAL_PROJECTS_DIR / "jirai-neko-demo" / "inputs", demo_dst / "inputs")
    shutil.copytree(
        REAL_PROJECTS_DIR / "jirai-neko-demo" / "runs" / "unpacked_run",
        demo_dst / "runs" / "unpacked_run",
    )

    with TestClient(main_mod.app) as client:
        # 1. Blank project name -> 422; valid create -> 200
        assert client.post("/api/projects", json={"name": "   "}).status_code == 422
        created = client.post("/api/projects", json={"name": "My Test Hero"})
        assert created.status_code == 200
        pid = created.json()["id"]
        assert pid == "my-test-hero"

        # 2. Missing project & unsafe path segments -> 404 / 400
        assert client.get("/api/projects/no-such-project").status_code == 404
        assert client.get("/api/projects/..").status_code in (400, 404)
        assert client.get("/api/projects/bad:id").status_code == 400
        assert client.post(f"/api/projects/{pid}/select-run", json={"run_id": "../secret"}).status_code == 400
        assert client.post(f"/api/projects/{pid}/select-run", json={"run_id": "missing_run"}).status_code == 404

        # 3. Upload validation: unsupported extension -> 415, empty -> 400, corrupt -> 400 (not saved!)
        r_415 = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("script.txt", b"hello", "text/plain")},
        )
        assert r_415.status_code == 415

        r_empty = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("empty.png", b"", "image/png")},
        )
        assert r_empty.status_code == 400

        r_corrupt = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("broken.png", b"not-a-png", "image/png")},
        )
        assert r_corrupt.status_code == 400
        assert not (isolated_projects / pid / "inputs" / "broken.png").exists()

        # Valid opaque upload succeeds (200) and triggers 422 OPAQUE_WALL gate on /work auto
        opaque_bytes = _make_rgba_bytes((96, 96), bg=(240, 240, 250, 255))
        r_opaque = client.post(
            f"/api/projects/{pid}/upload",
            files={"file": ("opaque_ref.png", opaque_bytes, "image/png")},
        )
        assert r_opaque.status_code == 200
        assert r_opaque.json()["detection"]["error_code"] == "OPAQUE_WALL"

        r_gate = client.post(f"/api/projects/{pid}/work", json={"mode": "auto"})
        assert r_gate.status_code == 422
        assert r_gate.json()["detail"]["error_code"] == "OPAQUE_WALL"

        # 4. /work input validation: unsafe input_name -> 400; empty project with no input/prompt -> 422 NO_INPUT
        assert client.post(f"/api/projects/{pid}/work", json={"input_name": "../project.json"}).status_code == 400
        empty_proj = client.post("/api/projects", json={"name": "Empty One"}).json()["id"]
        r_no_inp = client.post(f"/api/projects/{empty_proj}/work", json={"mode": "auto"})
        assert r_no_inp.status_code == 422
        assert r_no_inp.json()["detail"]["error_code"] == "NO_INPUT"

        # 5. Exit 75 on /work returns 503 while preserving top-level exit_code & error_code for frontend modal
        monkeypatch.setattr(
            main_mod,
            "generate_base_image_from_prompt",
            lambda *a, **kw: {
                "ok": False,
                "exit_code": 75,
                "error_code": "CODEX_UNAVAILABLE",
                "ask": {"cause": "login"},
                "message_vi": "Codex login required",
            },
        )
        r_75 = client.post(
            f"/api/projects/{empty_proj}/work",
            json={"mode": "prompt_to_sprite", "prompt": "chibi mage"},
        )
        assert r_75.status_code == 503
        body_75 = r_75.json()
        assert body_75["exit_code"] == 75
        assert body_75["error_code"] == "CODEX_UNAVAILABLE"
        assert body_75["ask"] == {"cause": "login"}

        # 6. Malformed manifest on /export-code and /ai-code -> 422; missing run -> 404; bad engine -> 400
        bad_run_dir = isolated_projects / pid / "runs" / "corrupt_manifest"
        bad_run_dir.mkdir(parents=True)
        (bad_run_dir / "manifest.json").write_text('{"animation": "invalid"}', encoding="utf-8")

        assert (
            client.get(f"/api/projects/{pid}/export-code?engine=html5&run_id=corrupt_manifest").status_code == 422
        )
        assert (
            client.post(f"/api/projects/{pid}/ai-code", json={"run_id": "corrupt_manifest"}).status_code == 422
        )
        assert client.get(f"/api/projects/{pid}/export-code?engine=html5&run_id=no_run").status_code == 404
        assert (
            client.get("/api/projects/jirai-neko-demo/export-code?engine=bad_engine&run_id=unpacked_run").status_code
            == 400
        )

        # 7. Background tile endpoint: corrupt image -> 400, valid image -> 200
        assert (
            client.post(
                f"/api/projects/{pid}/background-tile",
                files={"file": ("bad_bg.png", b"corrupt", "image/png")},
            ).status_code
            == 400
        )
        valid_bg = _make_rgba_bytes((320, 160), bg=(30, 28, 48, 255))
        r_bg = client.post(
            f"/api/projects/{pid}/background-tile",
            files={"file": ("city_bg.png", valid_bg, "image/png")},
        )
        assert r_bg.status_code == 200
        assert r_bg.json()["ok"] is True

        # 8. End-to-end /stabilize -> /frame-edit -> /reset-curation on isolated jirai-neko-demo
        r_stab = client.post(
            "/api/projects/jirai-neko-demo/stabilize",
            json={"run_id": "unpacked_run", "drop_stalled": True, "enable_idle_breathe": True, "breathe_mode": "pixel"},
        )
        assert r_stab.status_code == 200
        walk_summary = r_stab.json()["project"]["run_detail"]["analysis"]["states"]["walk"]["summary"]
        assert walk_summary["head_drift_frames"] == 0
        assert walk_summary["stalled_frames"] == 0

        r_edit = client.post(
            "/api/projects/jirai-neko-demo/frame-edit",
            json={"run_id": "unpacked_run", "state": "walk", "frame_index": 0, "delta_dx": 1, "delta_dy": 0},
        )
        assert r_edit.status_code == 200
        assert (
            client.post(
                "/api/projects/jirai-neko-demo/frame-edit",
                json={"run_id": "unpacked_run", "state": "walk", "frame_index": 99},
            ).status_code
            == 422
        )

        r_reset = client.post("/api/projects/jirai-neko-demo/reset-curation", json={"run_id": "unpacked_run"})
        assert r_reset.status_code == 200
        assert not (demo_dst / "runs" / "unpacked_run" / "curation.json").exists()
