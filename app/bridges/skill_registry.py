"""Read-only Skill Registry for 2D Sprite Auto-Run Studio.

Scans installed skills in `~/.codex/skills` and `~/.gemini/config/skills` without copying
or modifying them, preserving original licenses (Apache-2.0) and preventing remote code execution.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.config import CODEX_SKILLS_DIR, GEMINI_SKILLS_DIR

FEATURED_GAME_SKILLS = {"sprite-gen", "generate2dsprite", "generate2dmap", "hatch-pet"}

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(md_text: str) -> dict[str, str]:
    """Parse basic key: value pairs from YAML frontmatter without external dependencies."""
    m = FRONTMATTER_RE.match(md_text)
    if not m:
        return {}
    block = m.group(1)
    out: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def list_installed_skills(featured_only: bool = False) -> list[dict[str, Any]]:
    """Return read-only metadata for locally installed skills."""
    seen: set[str] = set()
    skills: list[dict[str, Any]] = []

    for source_label, root_dir in [("codex", CODEX_SKILLS_DIR), ("gemini", GEMINI_SKILLS_DIR)]:
        if not root_dir.exists():
            continue
        for item in sorted(root_dir.iterdir()):
            if not item.is_dir() or item.name.startswith("."):
                continue
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                continue
            if item.name in seen:
                continue
            if featured_only and item.name not in FEATURED_GAME_SKILLS:
                continue

            try:
                raw = skill_md.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            fm = _parse_frontmatter(raw)
            name = fm.get("name", item.name)
            desc = fm.get("description", "")
            lic = fm.get("license", "Apache-2.0" if (item / "LICENSE.txt").exists() else "Local Skill")

            seen.add(item.name)
            skills.append(
                {
                    "id": item.name,
                    "name": name,
                    "version": fm.get("version", "1.0.0"),
                    "description": desc,
                    "license": lic,
                    "source": source_label,
                    "path": str(item),
                    "skill_md_path": str(skill_md),
                    "is_featured_2d": item.name in FEATURED_GAME_SKILLS,
                }
            )

    # Sort featured 2D skills first
    skills.sort(key=lambda s: (0 if s["is_featured_2d"] else 1, s["id"]))
    return skills


def read_skill_preview(skill_id: str, max_chars: int = 4000) -> dict[str, Any]:
    """Read-only preview of a local skill's SKILL.md content."""
    for s in list_installed_skills(featured_only=False):
        if s["id"] == skill_id:
            p = Path(s["skill_md_path"])
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                return {"ok": False, "error": f"Cannot read SKILL.md for '{skill_id}': {exc}"}
            return {
                "ok": True,
                "skill": s,
                "preview": text[:max_chars],
                "truncated": len(text) > max_chars,
            }
    return {"ok": False, "error": f"Skill '{skill_id}' not found in local skill directories."}
