"""Bridge to Codex CLI (`codex.exe`) and `sprite-gen` providers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from app.config import find_codex_binary
from app.core.pipeline_runner import run_sprite_gen_cmd


def get_codex_status() -> dict[str, Any]:
    """Check if codex CLI is installed and signed in."""
    codex_bin = find_codex_binary()
    if not codex_bin:
        return {
            "installed": False,
            "logged_in": False,
            "binary": None,
            "status_text": "Không tìm thấy codex.exe",
        }
    try:
        proc = subprocess.run(
            [codex_bin, "login", "status"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        out = (proc.stdout + " " + proc.stderr).strip()
        logged_in = proc.returncode == 0 and ("logged in" in out.lower() or "chatgpt" in out.lower())
        return {
            "installed": True,
            "logged_in": logged_in,
            "binary": codex_bin,
            "status_text": out or ("Ready" if logged_in else "Not logged in"),
        }
    except Exception as exc:
        return {
            "installed": True,
            "logged_in": False,
            "binary": codex_bin,
            "status_text": f"Error checking codex login: {exc}",
        }


def generate_base_image_from_prompt(
    prompt: str,
    out_png: str | Path,
    direction: str = "side",
    facing: str = "right",
    provider: str = "codex",
) -> dict[str, Any]:
    """Use `sprite-gen gen` to create a single transparent standing base sprite from a text prompt."""
    out_path = Path(out_png)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "gen",
        "--provider",
        provider,
        "--prompt",
        prompt,
        "--transparent",
        "--trim-alpha",
        "--direction",
        direction,
        "--output",
        str(out_path),
    ]
    if direction in ("side", "front_diagonal", "back_diagonal"):
        args.extend(["--facing", facing])
    return run_sprite_gen_cmd(args, timeout=300)
