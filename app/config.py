"""Configuration and path discovery for 2D Sprite Auto-Run Studio."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parents[1]
PROJECTS_DIR = STUDIO_ROOT / "projects"
WEB_DIR = STUDIO_ROOT / "web"

USER_HOME = Path.home()
CODEX_SKILLS_DIR = USER_HOME / ".codex" / "skills"
GEMINI_SKILLS_DIR = USER_HOME / ".gemini" / "config" / "skills"

# Canonical sprite-gen installation (read-only reference, Apache-2.0)
SPRITE_GEN_ROOT = Path(
    os.environ.get(
        "SPRITE_GEN_ROOT",
        str(CODEX_SKILLS_DIR / "sprite-gen" if (CODEX_SKILLS_DIR / "sprite-gen").exists() else GEMINI_SKILLS_DIR / "sprite-gen"),
    )
)

SPRITE_GEN_VENV_BIN = SPRITE_GEN_ROOT / ".venv" / "bin"
SPRITE_GEN_PYTHON = SPRITE_GEN_VENV_BIN / ("python.exe" if os.name == "nt" else "python")
SPRITE_GEN_EXE = SPRITE_GEN_VENV_BIN / ("sprite-gen.exe" if os.name == "nt" else "sprite-gen")


def find_codex_binary() -> str | None:
    """Locate codex CLI executable on PATH or standard install path."""
    found = shutil.which("codex")
    if found:
        return found
    win_default = USER_HOME / "AppData" / "Local" / "Programs" / "OpenAI" / "Codex" / "bin" / "codex.exe"
    if win_default.exists():
        return str(win_default)
    return None


def find_antigravity_binaries() -> dict[str, str | None]:
    """Locate Antigravity CLI (`agy`) and Antigravity IDE launcher if present."""
    agy_cli = shutil.which("agy")
    ide_cmd = shutil.which("antigravity-ide")
    if not ide_cmd:
        candidate = USER_HOME / "AppData" / "Local" / "Programs" / "Antigravity IDE" / "bin" / "antigravity-ide.cmd"
        if candidate.exists():
            ide_cmd = str(candidate)
    app_exe = USER_HOME / "AppData" / "Local" / "Programs" / "antigravity" / "Antigravity.exe"
    return {
        "agy_cli": agy_cli,
        "antigravity_ide": ide_cmd,
        "antigravity_app": str(app_exe) if app_exe.exists() else None,
    }


HOST = "127.0.0.1"
PORT = int(os.environ.get("STUDIO_PORT", "8780"))

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
