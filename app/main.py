"""FastAPI Server for 2D Sprite Auto-Run Studio (bound strictly to 127.0.0.1)."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.bridges.codex_bridge import generate_base_image_from_prompt, get_codex_status
from app.bridges.ide_bridge import get_antigravity_status, open_in_antigravity_ide
from app.bridges.skill_registry import list_installed_skills, read_skill_preview
from app.config import HOST, PORT, PROJECTS_DIR, SPRITE_GEN_ROOT, WEB_DIR
from app.core.auto_stabilizer import apply_auto_stabilize, apply_manual_frame_edit
from app.core.detector import analyze_input_image
from app.core.pipeline_runner import (
    build_states_spec,
    interpolate_inbetween_frame,
    make_seamless_background_tile,
    recompose_run,
    reroll_single_state,
    run_ai_sprite_pipeline,
    run_cutout_on_image,
    unpack_existing_sheet,
)
from app.exporters.ai_codegen import generate_custom_sandbox_html
from app.exporters.asset_exporter import generate_forward_loop_gifs
from app.exporters.template_codegen import export_code_by_engine
from app.project_manager import (
    create_project,
    ensure_default_demo_project,
    get_project_details,
    get_run_details,
    list_projects,
    update_project_meta,
)

from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(app_instance: FastAPI):
    ensure_default_demo_project()
    yield


app = FastAPI(title="Aika 2D Sprite Auto-Run Studio", version="2.0.0", lifespan=_lifespan)

# Global SSE event subscribers
_sse_queues: list[asyncio.Queue[dict[str, Any]]] = []


def broadcast_event(event: dict[str, Any]) -> None:
    """Push a progress or status event to all connected SSE clients."""
    for q in list(_sse_queues):
        try:
            q.put_nowait(event)
        except Exception:
            pass


class CreateProjectReq(BaseModel):
    name: str
    prompt: str = ""
    default_skill: str = "sprite-gen"


class SelectRunReq(BaseModel):
    run_id: str


class WorkReq(BaseModel):
    mode: str = "auto"  # "auto" | "slice" | "ai_regen" | "prompt_to_sprite" | "cutout"
    input_name: str | None = None
    prompt: str = ""
    skill_id: str = "sprite-gen"
    provider: str = "codex"
    states: str = "idle,walk"
    cell_size: int = 256


class StabilizeReq(BaseModel):
    run_id: str | None = None
    drop_stalled: bool = True
    enable_idle_breathe: bool = True
    breathe_mode: str = "smooth"


class InterpolateReq(BaseModel):
    run_id: str | None = None
    state: str = "walk"
    from_idx: int = 0
    to_idx: int = 1
    provider: str = "codex"


class AICodeReq(BaseModel):
    run_id: str | None = None
    prompt: str = "Thêm nhảy kép Space, bấm J bắn tim hồng, có thanh HP"
    pixel_art: bool = False


class FrameEditReq(BaseModel):
    run_id: str | None = None
    state: str = "walk"
    frame_index: int = 0
    delta_dx: int = 0
    delta_dy: int = 0
    toggle_selected: bool = False


class RerollStateReq(BaseModel):
    run_id: str | None = None
    state: str = "walk"
    provider: str = "codex"


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    """Return system readiness: Codex CLI, Antigravity IDE, sprite-gen root, and installed skills."""
    return {
        "ok": True,
        "host": HOST,
        "port": PORT,
        "sprite_gen_root": str(SPRITE_GEN_ROOT),
        "sprite_gen_ready": SPRITE_GEN_ROOT.exists(),
        "codex": get_codex_status(),
        "antigravity": get_antigravity_status(),
        "skills": list_installed_skills(featured_only=False),
    }


@app.get("/api/skills/{skill_id}")
async def api_skill_preview(skill_id: str) -> dict[str, Any]:
    res = read_skill_preview(skill_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res


@app.get("/api/events")
async def api_sse_events() -> StreamingResponse:
    """Server-Sent Events stream for real-time WORK progress updates."""
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    _sse_queues.append(q)

    async def event_gen():
        try:
            yield f"data: {json.dumps({'stage': 'connected', 'progress': 0, 'message': 'Connected to Studio SSE'})}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if q in _sse_queues:
                _sse_queues.remove(q)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/api/projects")
async def api_list_projects() -> dict[str, Any]:
    return {"ok": True, "projects": list_projects()}


@app.post("/api/projects")
async def api_create_project(req: CreateProjectReq) -> dict[str, Any]:
    return create_project(req.name, prompt=req.prompt, default_skill=req.default_skill)


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str) -> dict[str, Any]:
    res = get_project_details(project_id)
    if not res.get("ok"):
        raise HTTPException(status_code=404, detail=res.get("error"))
    return res


@app.post("/api/projects/{project_id}/select-run")
async def api_select_run(project_id: str, req: SelectRunReq) -> dict[str, Any]:
    update_project_meta(project_id, {"active_run": req.run_id})
    return get_project_details(project_id)


@app.post("/api/projects/{project_id}/upload")
async def api_upload_input(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    inputs_dir = pdir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "uploaded.png").name
    dest = inputs_dir / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    det = analyze_input_image(dest)
    update_project_meta(project_id, {"active_input": safe_name})
    return {
        "ok": True,
        "filename": safe_name,
        "detection": det,
        "project": get_project_details(project_id),
    }


@app.post("/api/projects/{project_id}/work")
async def api_run_work(project_id: str, req: WorkReq) -> dict[str, Any]:
    """Execute the smart ⚡ WORK pipeline: Auto-Detect -> Slice or AI Generate -> Analyze -> Loop."""
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    details = get_project_details(project_id)
    input_name = req.input_name or details.get("active_input")
    inputs_dir = pdir / "inputs"
    runs_dir = pdir / "runs"

    if req.prompt:
        update_project_meta(project_id, {"prompt": req.prompt, "default_skill": req.skill_id})

    # Branch 0: If user requested cutout on an opaque image
    if req.mode == "cutout" and input_name:
        src_img = inputs_dir / input_name
        out_img = inputs_dir / f"cutout_{Path(input_name).stem}.png"
        broadcast_event({"stage": "cutout", "progress": 30, "message": f"Đang tách nền tự động cho {input_name}..."})
        res_cut = await asyncio.to_thread(run_cutout_on_image, src_img, out_img)
        if not res_cut.get("ok"):
            raise HTTPException(status_code=422, detail=res_cut.get("stderr") or "Không thể tách nền tự động.")
        update_project_meta(project_id, {"active_input": out_img.name})
        input_name = out_img.name

    # Branch 3: Prompt-only (no input image or explicit prompt_to_sprite)
    if req.mode == "prompt_to_sprite" or (not input_name and req.prompt):
        prompt_text = req.prompt or details.get("prompt") or "2D chibi anime game character standing side-view facing right"
        base_out = inputs_dir / "ai_generated_base.png"
        broadcast_event({"stage": "gen-base", "progress": 15, "message": "Đang gọi Codex tạo ảnh nhân vật gốc (base.png)..."})
        res_base = await asyncio.to_thread(
            generate_base_image_from_prompt,
            prompt_text,
            base_out,
            provider=req.provider,
        )
        if not res_base.get("ok"):
            return res_base
        input_name = base_out.name
        update_project_meta(project_id, {"active_input": input_name})
        req.mode = "ai_regen"

    if not input_name or not (inputs_dir / input_name).exists():
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "NO_INPUT",
                "message_vi": "Chưa có ảnh đầu vào hoặc Prompt. Hãy kéo thả ảnh hoặc nhập Prompt trước khi bấm WORK!",
            },
        )

    input_path = inputs_dir / input_name
    det = analyze_input_image(input_path)

    # Error Gate: Invalid / Corrupt / Opaque Wall (unless user explicitly forces AI regen using it as reference)
    if not det.get("ok") and req.mode not in ("ai_regen",):
        raise HTTPException(status_code=422, detail=det)

    effective_mode = req.mode
    if effective_mode == "auto":
        effective_mode = "slice" if det.get("kind") == "sprite_sheet" else "ai_regen"

    # Branch 1: Instant Auto-Slice & Play (~2 seconds)
    if effective_mode == "slice":
        run_id = f"slice_{Path(input_name).stem}"
        target_run = runs_dir / run_id
        broadcast_event({"stage": "unpack", "progress": 35, "message": f"Đang tự động cắt frame từ {input_name}..."})
        res = await asyncio.to_thread(unpack_existing_sheet, input_path, target_run, req.states)
        if not res.get("ok"):
            return res
        broadcast_event({"stage": "analyze", "progress": 85, "message": "Đang chấm điểm từng frame (Head Drift & Leg Ratio)..."})
        await asyncio.to_thread(generate_forward_loop_gifs, target_run)
        update_project_meta(project_id, {"active_run": run_id, "active_input": input_name})
        broadcast_event({"stage": "done", "progress": 100, "message": "Đã cắt frame & phát Auto-Run Looping!"})
        return {
            "ok": True,
            "branch": "slice",
            "run_id": run_id,
            "detection": det,
            "project": get_project_details(project_id),
        }

    # Branch 2: 1-Still (or Reference) to Full Sprite via AI (`prepare` + `gen-set`)
    run_id = f"ai_{req.provider}_{int(time.time())}"
    target_run = runs_dir / run_id
    desc = req.prompt or details.get("prompt") or f"2D game character sprite matching {input_name}"
    chroma = det.get("recommended_chroma_key", "#00FF00")

    # If the user triggered AI regen while having a sprite sheet selected, use base_chibi.png or frame-0 if available
    base_img_for_ai = input_path
    if det.get("kind") == "sprite_sheet":
        if (inputs_dir / "base_chibi.png").exists():
            base_img_for_ai = inputs_dir / "base_chibi.png"
        elif details.get("active_run"):
            f0 = runs_dir / str(details["active_run"]) / "frames" / "idle" / "frame-0.png"
            if f0.exists():
                base_img_for_ai = f0

    res_ai = await asyncio.to_thread(
        run_ai_sprite_pipeline,
        target_run,
        project_id.replace("-", "_"),
        base_img_for_ai,
        desc,
        chroma_key=chroma,
        cell_size=req.cell_size,
        states_spec=build_states_spec(req.states),
        provider=req.provider,
        progress_cb=broadcast_event,
    )
    if not res_ai.get("ok"):
        return res_ai

    await asyncio.to_thread(generate_forward_loop_gifs, target_run)
    update_project_meta(project_id, {"active_run": run_id})
    return {
        "ok": True,
        "branch": "ai_regen",
        "run_id": run_id,
        "project": get_project_details(project_id),
    }


@app.post("/api/projects/{project_id}/stabilize")
async def api_stabilize_run(project_id: str, req: StabilizeReq) -> dict[str, Any]:
    """1-Click Auto-Stabilize: lock head drift, pin baseline, filter stalled frames, and bake breathe."""
    details = get_project_details(project_id)
    run_id = req.run_id or details.get("active_run")
    if not run_id:
        raise HTTPException(status_code=400, detail="No active run to stabilize")

    rdir = PROJECTS_DIR / project_id / "runs" / run_id
    broadcast_event({"stage": "stabilize", "progress": 40, "message": "Đang khóa trục đầu (dx/dy), lọc frame trùng & nướng nhịp thở Breathe..."})
    stab_res = await asyncio.to_thread(
        apply_auto_stabilize,
        rdir,
        drop_stalled=req.drop_stalled,
        enable_idle_breathe=req.enable_idle_breathe,
        breathe_mode=req.breathe_mode,
    )
    if not stab_res.get("ok"):
        raise HTTPException(status_code=400, detail=stab_res.get("error"))

    await asyncio.to_thread(recompose_run, rdir)
    await asyncio.to_thread(generate_forward_loop_gifs, rdir)
    broadcast_event({"stage": "done", "progress": 100, "message": "Đã ổn định chuyển động (Auto-Stabilize) thành công!"})
    return {
        "ok": True,
        "stabilize": stab_res,
        "project": get_project_details(project_id),
    }


@app.post("/api/projects/{project_id}/reset-curation")
async def api_reset_curation(project_id: str, req: SelectRunReq) -> dict[str, Any]:
    """Remove curation.json to restore original un-stabilized frames for before/after comparison."""
    rdir = PROJECTS_DIR / project_id / "runs" / req.run_id
    cpath = rdir / "curation.json"
    if cpath.exists():
        cpath.unlink()
        await asyncio.to_thread(recompose_run, rdir)
    return get_project_details(project_id)


@app.post("/api/projects/{project_id}/interpolate")
async def api_interpolate_frames(project_id: str, req: InterpolateReq) -> dict[str, Any]:
    """Generate AI in-between frame via scripts/interpolate_frames.py."""
    details = get_project_details(project_id)
    run_id = req.run_id or details.get("active_run")
    if not run_id:
        raise HTTPException(status_code=400, detail="No active run")
    rdir = PROJECTS_DIR / project_id / "runs" / run_id
    broadcast_event(
        {
            "stage": "interpolate",
            "progress": 45,
            "message": f"Đang gọi {req.provider} vẽ bù frame trung gian giữa #{req.from_idx} và #{req.to_idx}...",
        }
    )
    res = await asyncio.to_thread(
        interpolate_inbetween_frame,
        rdir,
        req.state,
        req.from_idx,
        req.to_idx,
        req.provider,
    )
    broadcast_event({"stage": "done", "progress": 100, "message": "Đã hoàn tất vẽ bù frame trung gian!"})
    return {"ok": res.get("ok"), "result": res, "project": get_project_details(project_id)}


@app.get("/api/projects/{project_id}/export-code")
async def api_export_code(
    project_id: str,
    engine: str = "html5",
    run_id: str | None = None,
    pixel_art: bool = False,
) -> dict[str, Any]:
    """Instant 0s code export for html5, phaser3, godot4, unity."""
    details = get_project_details(project_id)
    active_run = run_id or details.get("active_run")
    if not active_run:
        raise HTTPException(status_code=400, detail="No active run in project")

    rdir = PROJECTS_DIR / project_id / "runs" / active_run
    res = export_code_by_engine(rdir, engine=engine, embed_base64=True, pixel_art=pixel_art)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))

    # Also save exported file into project's exported_code/ folder
    out_dir = PROJECTS_DIR / project_id / "exported_code"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_file = out_dir / res["filename"]
    saved_file.write_text(res["code"], encoding="utf-8")
    res["saved_path"] = str(saved_file)
    res["download_url"] = f"/projects/{project_id}/exported_code/{res['filename']}"
    return res


@app.post("/api/projects/{project_id}/ai-code")
async def api_ai_custom_code(project_id: str, req: AICodeReq) -> dict[str, Any]:
    """Generate custom HTML5 Canvas gameplay code to preview in a sandboxed iframe."""
    details = get_project_details(project_id)
    active_run = req.run_id or details.get("active_run")
    if not active_run:
        raise HTTPException(status_code=400, detail="No active run in project")

    rdir = PROJECTS_DIR / project_id / "runs" / active_run
    res = generate_custom_sandbox_html(rdir, custom_prompt=req.prompt, pixel_art=req.pixel_art)
    out_dir = PROJECTS_DIR / project_id / "exported_code"
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_file = out_dir / res["filename"]
    saved_file.write_text(res["code"], encoding="utf-8")
    res["saved_path"] = str(saved_file)
    return res


@app.post("/api/projects/{project_id}/open-ide")
async def api_open_ide(project_id: str) -> dict[str, Any]:
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    return open_in_antigravity_ide(pdir)


@app.post("/api/projects/{project_id}/frame-edit")
async def api_frame_edit(project_id: str, req: FrameEditReq) -> dict[str, Any]:
    """Nudge a single frame's dx/dy or toggle selected status in curation.json and recompose."""
    details = get_project_details(project_id)
    run_id = req.run_id or details.get("active_run")
    if not run_id:
        raise HTTPException(status_code=400, detail="No active run")
    rdir = PROJECTS_DIR / project_id / "runs" / run_id
    res = await asyncio.to_thread(
        apply_manual_frame_edit,
        rdir,
        req.state,
        req.frame_index,
        req.delta_dx,
        req.delta_dy,
        req.toggle_selected,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    await asyncio.to_thread(recompose_run, rdir)
    return {"ok": True, "edit": res, "project": get_project_details(project_id)}


@app.post("/api/projects/{project_id}/reroll-state")
async def api_reroll_state(project_id: str, req: RerollStateReq) -> dict[str, Any]:
    """Regenerate only a single animation row (`gen-set --states <state> --force`)."""
    details = get_project_details(project_id)
    run_id = req.run_id or details.get("active_run")
    if not run_id:
        raise HTTPException(status_code=400, detail="No active run")
    rdir = PROJECTS_DIR / project_id / "runs" / run_id
    broadcast_event(
        {
            "stage": "reroll",
            "progress": 40,
            "message": f"Đang gọi {req.provider} vẽ lại riêng hàng '{req.state}'...",
        }
    )
    res = await asyncio.to_thread(reroll_single_state, rdir, req.state, req.provider)
    broadcast_event({"stage": "done", "progress": 100, "message": f"Đã vẽ lại xong hàng '{req.state}'!"})
    return {"ok": res.get("ok"), "result": res, "project": get_project_details(project_id)}


@app.post("/api/projects/{project_id}/background-tile")
async def api_background_tile(
    project_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Upload a background image and quilt it into a seamless repeating tile via `sprite-gen background-tile`."""
    pdir = PROJECTS_DIR / project_id
    if not pdir.exists():
        raise HTTPException(status_code=404, detail="Project not found")
    bg_dir = pdir / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)
    raw_bg = bg_dir / f"raw_{Path(file.filename or 'bg.png').name}"
    with raw_bg.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    tiled_bg = bg_dir / f"seamless_tile_{int(time.time())}.png"
    broadcast_event({"stage": "bg-tile", "progress": 50, "message": "Đang nối mí ảnh nền lặp vô tận (sprite-gen background-tile)..."})
    res = await asyncio.to_thread(make_seamless_background_tile, raw_bg, tiled_bg, 512, 32)
    broadcast_event({"stage": "done", "progress": 100, "message": "Đã tạo xong nền lặp vô tận (Seamless Tile)!"})
    tile_url = f"/projects/{project_id}/backgrounds/{tiled_bg.name}" if tiled_bg.exists() else f"/projects/{project_id}/backgrounds/{raw_bg.name}"
    return {"ok": True, "tile_url": tile_url, "report": res.get("data")}


# Mount static directories
app.mount("/projects", StaticFiles(directory=str(PROJECTS_DIR)), name="projects")
WEB_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/", StaticFiles(directory=str(WEB_DIR)), name="web")
