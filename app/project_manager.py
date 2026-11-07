"""Project Manager for 2D Sprite Auto-Run Studio."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from app.config import PROJECTS_DIR
from app.core.detector import analyze_input_image
from app.core.frame_analyzer import analyze_run_directory


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip().lower()).strip("-")
    return slug or f"project-{int(time.time())}"


def ensure_default_demo_project() -> None:
    """Ensure `jirai-neko-demo` has a valid `project.json` if its directory exists."""
    demo_dir = PROJECTS_DIR / "jirai-neko-demo"
    if not demo_dir.exists():
        return
    pjson = demo_dir / "project.json"
    if not pjson.exists():
        default_meta = {
            "id": "jirai-neko-demo",
            "name": "Jirai-kei Neko Chibi (Demo)",
            "created_at": "2026-11-06T17:00:00+09:00",
            "active_input": "input_sheet.png",
            "active_run": "codex_run" if (demo_dir / "runs" / "codex_run").exists() else "unpacked_run",
            "default_skill": "sprite-gen",
            "prompt": (
                "2D chibi side-view anime game sprite of a Jirai-kei x Ryousangata x Cat-motif girl "
                "(黒×ピンクの地雷系美少女, 157cm petite chibi proportions) facing right: black hair with pink "
                "gradient tips in long wavy twintails, straight bangs, large pastel pink ribbon and white "
                "cat-shaped hairclip, pink-purple eyes with heart highlights, black oversized hoodie with "
                "pink criss-cross ribbon lacing on sleeves, black-and-pink plaid pleated mini skirt, "
                "black lace knee-high socks, and black platform boots"
            ),
        }
        pjson.write_text(json.dumps(default_meta, indent=2, ensure_ascii=False), encoding="utf-8")


def list_projects() -> list[dict[str, Any]]:
    """Return all projects in `projects/`."""
    ensure_default_demo_project()
    projects: list[dict[str, Any]] = []
    if not PROJECTS_DIR.exists():
        return projects

    for pdir in sorted(PROJECTS_DIR.iterdir()):
        if not pdir.is_dir() or pdir.name.startswith("."):
            continue
        meta = get_project_details(pdir.name)
        if meta.get("ok"):
            projects.append(meta)
    # Put jirai-neko-demo first
    projects.sort(key=lambda x: (0 if x["id"] == "jirai-neko-demo" else 1, x["id"]))
    return projects


def create_project(name: str, prompt: str = "", default_skill: str = "sprite-gen") -> dict[str, Any]:
    """Create a new project directory structure."""
    pid = _slugify(name)
    pdir = PROJECTS_DIR / pid
    (pdir / "inputs").mkdir(parents=True, exist_ok=True)
    (pdir / "runs").mkdir(parents=True, exist_ok=True)
    (pdir / "exported_code").mkdir(parents=True, exist_ok=True)

    meta = {
        "id": pid,
        "name": name.strip() or pid,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "active_input": None,
        "active_run": None,
        "default_skill": default_skill,
        "prompt": prompt,
    }
    (pdir / "project.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return get_project_details(pid)


def update_project_meta(project_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update fields in project.json."""
    pdir = PROJECTS_DIR / project_id
    pjson = pdir / "project.json"
    meta: dict[str, Any] = {"id": project_id, "name": project_id}
    if pjson.exists():
        try:
            meta = json.loads(pjson.read_text(encoding="utf-8"))
        except Exception:
            pass
    meta.update(updates)
    pjson.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def get_project_details(project_id: str) -> dict[str, Any]:
    """Load complete details, inputs, runs, and active run manifest/analysis for a project."""
    ensure_default_demo_project()
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        return {"ok": False, "error": f"Project '{project_id}' not found."}

    pjson = pdir / "project.json"
    meta: dict[str, Any] = {"id": project_id, "name": project_id}
    if pjson.exists():
        try:
            meta = json.loads(pjson.read_text(encoding="utf-8"))
        except Exception:
            pass

    inputs_dir = pdir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    inputs_list: list[dict[str, Any]] = []
    for f in sorted(inputs_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            det = analyze_input_image(f)
            inputs_list.append(
                {
                    "name": f.name,
                    "url": f"/projects/{project_id}/inputs/{f.name}",
                    "detection": det,
                }
            )

    runs_dir = pdir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    runs_list: list[dict[str, Any]] = []
    for r in sorted(runs_dir.iterdir()):
        if r.is_dir() and (r / "manifest.json").exists():
            runs_list.append(
                {
                    "id": r.name,
                    "has_curation": (r / "curation.json").exists(),
                    "atlas_url": f"/projects/{project_id}/runs/{r.name}/sprite-sheet-alpha.png",
                }
            )

    active_run = meta.get("active_run")
    if (not active_run or not (runs_dir / str(active_run) / "manifest.json").exists()) and runs_list:
        active_run = runs_list[0]["id"]

    active_input = meta.get("active_input")
    if (not active_input or not (inputs_dir / str(active_input)).exists()) and inputs_list:
        active_input = inputs_list[0]["name"]

    run_detail: dict[str, Any] | None = None
    if active_run and (runs_dir / active_run / "manifest.json").exists():
        run_detail = get_run_details(project_id, active_run)

    return {
        "ok": True,
        "id": project_id,
        "name": meta.get("name", project_id),
        "prompt": meta.get("prompt", ""),
        "default_skill": meta.get("default_skill", "sprite-gen"),
        "active_input": active_input,
        "active_run": active_run,
        "inputs": inputs_list,
        "runs": runs_list,
        "run_detail": run_detail,
    }


def get_run_details(project_id: str, run_id: str) -> dict[str, Any]:
    """Load manifest.json, frame analysis, and preview URLs for a specific run."""
    rdir = PROJECTS_DIR / project_id / "runs" / run_id
    mpath = rdir / "manifest.json"
    if not mpath.exists():
        return {"ok": False, "error": f"Run '{run_id}' has no manifest.json"}

    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    analysis = analyze_run_directory(rdir)
    ts = int(time.time() * 1000)

    previews: dict[str, str] = {}
    prev_dir = rdir / "previews"
    if prev_dir.exists():
        for g in sorted(prev_dir.glob("*.gif")):
            previews[g.stem] = f"/projects/{project_id}/runs/{run_id}/previews/{g.name}?t={ts}"

    # Frame URLs per state
    frame_urls: dict[str, list[str]] = {}
    frames_root = rdir / "frames"
    if frames_root.exists():
        for sdir in sorted(frames_root.iterdir()):
            if sdir.is_dir() and not sdir.name.startswith("_"):
                pngs = sorted(sdir.glob("frame-*.png"), key=lambda p: int(p.stem.split("-")[1]))
                frame_urls[sdir.name] = [
                    f"/projects/{project_id}/runs/{run_id}/frames/{sdir.name}/{p.name}?t={ts}" for p in pngs
                ]

    return {
        "ok": True,
        "project_id": project_id,
        "run_id": run_id,
        "atlas_url": f"/projects/{project_id}/runs/{run_id}/sprite-sheet-alpha.png?t={ts}",
        "manifest_url": f"/projects/{project_id}/runs/{run_id}/manifest.json?t={ts}",
        "aseprite_url": (
            f"/projects/{project_id}/runs/{run_id}/exports/aseprite.json?t={ts}"
            if (rdir / "exports" / "aseprite.json").exists()
            else None
        ),
        "manifest": manifest,
        "analysis": analysis,
        "previews": previews,
        "frame_urls": frame_urls,
    }
