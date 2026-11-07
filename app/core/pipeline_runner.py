"""Wrapper around sprite-gen CLI commands for deterministic sprite execution."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image, UnidentifiedImageError

from app.config import SPRITE_GEN_EXE, SPRITE_GEN_PYTHON, SPRITE_GEN_ROOT

EXIT_75_RE = re.compile(r"sprite-gen ask codex-unavailable:\s*(\{.*\})")

STATE_PRESETS: dict[str, dict[str, Any]] = {
    "idle": {
        "frames": 4,
        "fps": 5,
        "loop": True,
        "action": "side-view facing right, subtle idle breathing, gentle hair sway, and one soft eye blink while feet stay planted on the ground line",
    },
    "walk": {
        "frames": 6,
        "fps": 8,
        "loop": True,
        "action": "side-view facing right, smooth even 6-frame walking cycle in place: alternating left-foot and right-foot steps, natural opposite arm swing, strictly consistent head height",
    },
    "run": {
        "frames": 6,
        "fps": 10,
        "loop": True,
        "action": "side-view facing right, energetic 6-frame running cycle in place: slight forward torso lean, clear alternating stride and arm pump, consistent head height",
    },
    "jump": {
        "frames": 4,
        "fps": 8,
        "loop": False,
        "action": "side-view facing right, 4-frame jump sequence: crouch preparation, upward takeoff, airborne peak pose, soft landing crouch",
    },
    "attack": {
        "frames": 4,
        "fps": 8,
        "loop": False,
        "action": "side-view facing right, 4-frame melee attack sequence: windup, forward strike, impact extension, recovery pose with no detached projectiles",
    },
}


def build_states_spec(states_csv: str) -> dict[str, dict[str, Any]]:
    """Build states dictionary from comma-separated state names using canonical presets."""
    names = [s.strip().lower() for s in states_csv.split(",") if s.strip()]
    if not names:
        names = ["idle", "walk"]
    out: dict[str, dict[str, Any]] = {}
    for n in names:
        if n in STATE_PRESETS:
            out[n] = dict(STATE_PRESETS[n])
        else:
            out[n] = {
                "frames": 4,
                "fps": 6,
                "loop": True,
                "action": f"side-view facing right, clean {n} animation sequence in place with consistent body proportions",
            }
    return out


def _subprocess_failure(cmd: list[str], exc: BaseException, timeout: int) -> dict[str, Any]:
    """Build a structured failure result for a subprocess that could not run to completion."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return {
            "ok": False,
            "exit_code": None,
            "error_code": "TIMEOUT",
            "data": None,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s: {cmd[0]}",
            "message_vi": f"Lệnh sprite-gen chạy quá thời gian cho phép ({timeout}s).",
        }
    return {
        "ok": False,
        "exit_code": None,
        "error_code": "SPRITE_GEN_MISSING",
        "data": None,
        "stdout": "",
        "stderr": f"Cannot execute {cmd[0]}: {exc}",
        "message_vi": (
            "Không chạy được sprite-gen. Hãy kiểm tra SPRITE_GEN_ROOT và môi trường .venv của sprite-gen."
        ),
    }


def _run_subprocess(cmd: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str] | dict[str, Any]:
    """Run a command, returning either the completed process or a structured failure dict."""
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # OSError covers FileNotFoundError / PermissionError (missing binary or cwd).
        return _subprocess_failure(cmd, exc, timeout)


def _check_exit_75(proc: subprocess.CompletedProcess[str]) -> dict[str, Any] | None:
    """Return a structured CODEX_UNAVAILABLE payload if proc exited with code 75 or emitted codex-unavailable."""
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    if proc.returncode == 75 or "codex-unavailable:" in stderr or "codex-unavailable:" in stdout:
        combined = f"{stderr}\n{stdout}"
        m = EXIT_75_RE.search(combined)
        ask_payload: dict[str, Any] = {"cause": "login"}
        if m:
            try:
                parsed = json.loads(m.group(1))
                if isinstance(parsed, dict):
                    ask_payload = parsed
            except Exception:
                pass
        return {
            "ok": False,
            "exit_code": 75,
            "error_code": "CODEX_UNAVAILABLE",
            "ask": ask_payload,
            "stdout": stdout,
            "stderr": stderr,
            "message_vi": (
                "Codex CLI hiện chưa đăng nhập hoặc đã hết hạn mức sử dụng (Exit 75). "
                "Vui lòng chọn: (1) Đăng nhập lại `codex login`, (2) Chuyển sang Grok / OpenAI API, hoặc (3) Tạm dừng."
            ),
        }
    return None


def run_sprite_gen_cmd(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    """Run a sprite-gen CLI subcommand and parse JSON/stdout/stderr, catching Exit 75."""
    cmd = [str(SPRITE_GEN_EXE), *args]
    proc = _run_subprocess(cmd, cwd or SPRITE_GEN_ROOT, timeout)
    if isinstance(proc, dict):
        return proc
    exit_75 = _check_exit_75(proc)
    if exit_75 is not None:
        return exit_75
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    parsed_json: Any = None
    if stdout:
        # Try parsing last JSON block from stdout
        try:
            parsed_json = json.loads(stdout)
        except Exception:
            for idx in range(len(stdout) - 1, -1, -1):
                if stdout[idx] == "{":
                    try:
                        parsed_json = json.loads(stdout[idx:])
                        break
                    except Exception:
                        continue

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "data": parsed_json,
        "stdout": stdout,
        "stderr": stderr,
    }


def unpack_existing_sheet(
    sheet_path: str | Path,
    out_dir: str | Path,
    states: str = "idle,walk",
) -> dict[str, Any]:
    """Unpack an existing multi-frame sprite sheet into a run directory, compose atlas & GIFs."""
    rdir = Path(out_dir)
    rdir.mkdir(parents=True, exist_ok=True)

    res_unpack = run_sprite_gen_cmd(
        ["unpack-atlas", "--atlas", str(sheet_path), "--states", states, "--out-dir", str(rdir), "--force"]
    )
    if not res_unpack["ok"]:
        # Retry with auto single-row or auto-detect without explicit state names if needed
        res_unpack = run_sprite_gen_cmd(
            ["unpack-atlas", "--atlas", str(sheet_path), "--auto", "--out-dir", str(rdir), "--force"]
        )
        if not res_unpack["ok"]:
            return res_unpack

    res_atlas = run_sprite_gen_cmd(["compose-atlas", "--run-dir", str(rdir)])
    res_gif = run_sprite_gen_cmd(["compose-gif", "--run-dir", str(rdir), "--out-dir", str(rdir / "previews")])
    res_ase = run_sprite_gen_cmd(["export-aseprite", "--run-dir", str(rdir)])

    return {
        "ok": True,
        "run_dir": str(rdir),
        "unpack": res_unpack.get("data"),
        "atlas": res_atlas.get("data"),
        "gifs": res_gif.get("data"),
        "aseprite": res_ase.get("data"),
    }


def recompose_run(run_dir: str | Path) -> dict[str, Any]:
    """Re-run compose-atlas, compose-gif, and export-aseprite after curation/stabilization."""
    rdir = Path(run_dir)
    res_atlas = run_sprite_gen_cmd(["compose-atlas", "--run-dir", str(rdir)])
    res_gif = run_sprite_gen_cmd(["compose-gif", "--run-dir", str(rdir), "--out-dir", str(rdir / "previews")])
    res_ase = run_sprite_gen_cmd(["export-aseprite", "--run-dir", str(rdir)])
    return {
        "ok": res_atlas["ok"] and res_gif["ok"],
        "run_dir": str(rdir),
        "atlas": res_atlas.get("data"),
        "gifs": res_gif.get("data"),
        "aseprite": res_ase.get("data"),
    }


def run_cutout_on_image(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Run sprite-gen cutout to remove uniform background from an opaque image."""
    res = run_sprite_gen_cmd(["cutout", "--input", str(input_path), "--output", str(output_path)])
    return res


def run_ai_sprite_pipeline(
    run_dir: str | Path,
    character_id: str,
    base_image: str | Path,
    description: str,
    style: str = "high-quality 2D anime game sprite, clean uniform lineart, consistent proportions across every frame",
    chroma_key: str = "#00FF00",
    cell_size: int = 256,
    states_spec: dict[str, Any] | None = None,
    provider: str = "codex",
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Execute the full AI sprite-gen pipeline (prepare -> gen-set -> extract -> compose-atlas -> compose-gif -> inspect)."""
    rdir = Path(run_dir)
    rdir.mkdir(parents=True, exist_ok=True)

    def emit(stage: str, pct: int, msg: str, extra: dict[str, Any] | None = None) -> None:
        if progress_cb:
            payload = {"stage": stage, "progress": pct, "message": msg}
            if extra:
                payload.update(extra)
            progress_cb(payload)

    if not states_spec:
        states_spec = build_states_spec("idle,walk")

    req_file = rdir.parent / f"{character_id}_request.json"
    req_file.write_text(json.dumps({"states": states_spec}, indent=2), encoding="utf-8")

    emit("prepare", 10, "Đang chuẩn bị khung lưới hình học (layout guide) & cấu hình chroma key...")
    res_prep = run_sprite_gen_cmd(
        [
            "prepare",
            "--out-dir",
            str(rdir),
            "--character-id",
            character_id,
            "--base-image",
            str(base_image),
            "--description",
            description,
            "--style",
            style,
            "--chroma-key",
            chroma_key,
            "--cell-width",
            str(cell_size),
            "--cell-height",
            str(cell_size),
            "--fit-resample",
            "lanczos",
            "--fit-align-x",
            "centroid",
            "--fit-align-y",
            "bottom",
            "--no-fit-pixel-unfake",
            "--request",
            str(req_file),
            "--force",
        ]
    )
    if not res_prep["ok"]:
        emit("error", 10, f"Lỗi ở bước prepare: {res_prep.get('stderr') or res_prep.get('stdout')}")
        return res_prep

    emit("gen-set", 25, f"Đang gọi {provider} vẽ các hàng chuyển động ({', '.join(states_spec.keys())})...")
    res_gen = run_sprite_gen_cmd(["gen-set", "--run-dir", str(rdir), "--provider", provider], timeout=600)
    if not res_gen["ok"]:
        emit("error", 40, res_gen.get("message_vi") or f"Lỗi khi chạy gen-set: {res_gen.get('stderr')}")
        return res_gen

    emit("extract", 70, "Đang tách nền chroma 4 bước & căn chỉnh nhân vật vào ô...")
    res_ext = run_sprite_gen_cmd(["extract", "--run-dir", str(rdir)])

    emit("compose", 85, "Đang đóng gói Sprite Atlas, tạo GIF động và xuất Aseprite JSON...")
    res_atlas = run_sprite_gen_cmd(["compose-atlas", "--run-dir", str(rdir)])
    res_gif = run_sprite_gen_cmd(["compose-gif", "--run-dir", str(rdir), "--out-dir", str(rdir / "previews")])
    res_ase = run_sprite_gen_cmd(["export-aseprite", "--run-dir", str(rdir)])
    res_ins = run_sprite_gen_cmd(["inspect", "--run-dir", str(rdir)])

    emit("done", 100, "Hoàn tất quy trình tạo Sprite bằng AI!")
    return {
        "ok": res_atlas["ok"],
        "run_dir": str(rdir),
        "extract": res_ext.get("data"),
        "atlas": res_atlas.get("data"),
        "gifs": res_gif.get("data"),
        "aseprite": res_ase.get("data"),
        "inspect": res_ins.get("data"),
    }


def interpolate_inbetween_frame(
    run_dir: str | Path,
    state: str,
    from_idx: int,
    to_idx: int,
    provider: str = "codex",
) -> dict[str, Any]:
    """Call scripts/interpolate_frames.py to generate an AI in-between frame for a JUMP_CUT gap."""
    script_path = SPRITE_GEN_ROOT / "scripts" / "interpolate_frames.py"
    cmd = [
        str(SPRITE_GEN_PYTHON),
        str(script_path),
        "--run-dir",
        str(run_dir),
        "--state",
        state,
        "--between",
        str(from_idx),
        str(to_idx),
        "--provider",
        provider,
        "--extract",
    ]
    proc = _run_subprocess(cmd, SPRITE_GEN_ROOT, 300)
    if isinstance(proc, dict):
        return proc
    exit_75 = _check_exit_75(proc)
    if exit_75 is not None:
        return exit_75
    if proc.returncode == 0:
        recompose_run(run_dir)
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def reroll_single_state(
    run_dir: str | Path,
    state_name: str,
    provider: str = "codex",
) -> dict[str, Any]:
    """Regenerate only one specific state row (`gen-set --states <state> --force`) and re-extract."""
    rdir = Path(run_dir)
    res_gen = run_sprite_gen_cmd(
        ["gen-set", "--run-dir", str(rdir), "--states", state_name, "--provider", provider, "--force"],
        timeout=300,
    )
    if not res_gen["ok"]:
        return res_gen
    res_ext = run_sprite_gen_cmd(["extract", "--run-dir", str(rdir)])
    res_comp = recompose_run(rdir)
    return {
        "ok": res_comp["ok"],
        "state": state_name,
        "extract": res_ext.get("data"),
        "compose": res_comp,
    }


def _fallback_horizontal_tile(
    prep_path: Path,
    out_path: Path,
    period: int,
    overlap: int,
    report_path: Path,
) -> dict[str, Any]:
    """Create a horizontally seamless `period`-wide RGBA tile via smooth cosine overlap blending."""
    with Image.open(prep_path) as im:
        arr = np.asarray(im.convert("RGBA"), dtype=np.float32)

    h, _, _ = arr.shape
    tile = arr[:, :period, :].copy()
    tail = arr[:, period : period + overlap, :]
    weights = (0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, overlap, dtype=np.float32)))[None, :, None]
    # At x=0, weight=0 -> pixel comes from tail[:, 0] == arr[:, period], matching tile[:, period-1]'s neighbor!
    tile[:, :overlap, :] = tail * (1.0 - weights) + tile[:, :overlap, :] * weights
    out_u8 = np.clip(np.round(tile), 0, 255).astype(np.uint8)
    Image.fromarray(out_u8, mode="RGBA").save(out_path)

    report = {
        "ok": True,
        "engine": "pillow-cosine-fallback",
        "axis": "x",
        "period": period,
        "overlap": overlap,
        "width": period,
        "height": int(h),
        "out": str(out_path),
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "exit_code": 0,
        "data": report,
        "stdout": "",
        "stderr": "",
    }


def make_seamless_background_tile(
    source_path: str | Path,
    out_path: str | Path,
    period: int = 512,
    overlap: int = 32,
) -> dict[str, Any]:
    """Ensure source image meets period+overlap width and run `sprite-gen background-tile`."""
    if period < 16 or overlap < 1 or overlap >= period:
        return {
            "ok": False,
            "error_code": "INVALID_PARAMS",
            "stderr": f"Invalid period={period} / overlap={overlap} (require period >= 16 and 1 <= overlap < period).",
        }

    src = Path(source_path)
    if not src.is_file():
        return {"ok": False, "error_code": "FILE_NOT_FOUND", "stderr": f"Source image not found: {src}"}

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    min_w = period + overlap
    prep_path = out.parent / f"_prep_{src.stem}.png"
    try:
        with Image.open(src) as im:
            rgba = im.convert("RGBA")
            w, h = rgba.size
            if w < 2 or h < 2:
                return {"ok": False, "error_code": "INVALID_IMAGE", "stderr": f"Background image too small ({w}x{h})."}
            if w < min_w:
                scale = (min_w + 16) / max(1, w)
                rgba = rgba.resize((int(round(w * scale)), int(round(h * scale))), Image.Resampling.LANCZOS)
            rgba.save(prep_path)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return {"ok": False, "error_code": "CORRUPT_IMAGE", "stderr": f"Invalid background image: {exc}"}

    report_path = out.with_suffix(".report.json")
    try:
        res = run_sprite_gen_cmd(
            [
                "background-tile",
                "--source",
                str(prep_path),
                "--out",
                str(out),
                "--period",
                str(period),
                "--overlap",
                str(overlap),
                "--axis",
                "x",
                "--report",
                str(report_path),
            ]
        )
        if res.get("error_code") == "SPRITE_GEN_MISSING":
            res = _fallback_horizontal_tile(prep_path, out, period, overlap, report_path)
        return res
    finally:
        if prep_path.exists():
            try:
                prep_path.unlink()
            except OSError:
                pass

