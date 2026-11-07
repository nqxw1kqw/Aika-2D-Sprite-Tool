"""Bridge to Antigravity IDE / CLI (`agy`) and OS folder openers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from app.config import find_antigravity_binaries


def get_antigravity_status() -> dict[str, Any]:
    """Return availability of Antigravity CLI (`agy`) and Antigravity IDE on this machine."""
    bins = find_antigravity_binaries()
    return {
        "agy_cli": bins["agy_cli"],
        "antigravity_ide": bins["antigravity_ide"],
        "antigravity_app": bins["antigravity_app"],
        "ide_ready": bool(bins["antigravity_ide"] or bins["antigravity_app"]),
        "note_vi": (
            "Antigravity IDE đã sẵn sàng để mở Project. "
            "Lưu ý theo chuẩn sprite-gen (PR #36): việc sinh ảnh tự động dùng `codex.exe` (ChatGPT OAuth) hoặc API key hợp lệ."
        ),
    }


def open_in_antigravity_ide(target_path: str | Path) -> dict[str, Any]:
    """Open a project folder or file in Antigravity IDE (or Explorer if IDE launcher is absent)."""
    resolved = Path(target_path).resolve()
    if not resolved.exists():
        return {"ok": False, "error": f"Target path does not exist: {resolved}"}

    bins = find_antigravity_binaries()
    path_str = str(resolved)
    ide_cmd = bins.get("antigravity_ide")
    if ide_cmd and Path(ide_cmd).exists():
        try:
            if os.name == "nt" and ide_cmd.lower().endswith((".cmd", ".bat")):
                cmd = [os.environ.get("COMSPEC", "cmd.exe"), "/c", ide_cmd, path_str]
            else:
                cmd = [ide_cmd, path_str]
            subprocess.Popen(cmd, shell=False)
            return {"ok": True, "opened_with": "antigravity-ide", "target": path_str}
        except OSError as exc:
            return {"ok": False, "error": f"Failed to launch IDE: {exc}"}
    if os.name == "nt":
        os.startfile(path_str)
        return {"ok": True, "opened_with": "explorer", "target": path_str}
    return {"ok": False, "error": "No IDE launcher found."}
