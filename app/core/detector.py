"""Auto-Detector for 2D Sprite Auto-Run Studio.

Validates uploaded images and classifies them into:
- `invalid`: Corrupted, completely transparent, or unkeyed solid background wall
- `single_still`: A single character figure (1x1) -> needs AI row generation (`prepare` + `gen-set`)
- `sprite_sheet`: Multiple separated character figures (MxN) -> ready for immediate `unpack-atlas` & looping
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError


def _find_1d_runs(mask_1d: np.ndarray, min_len: int = 4, min_gap: int = 2) -> list[tuple[int, int]]:
    """Find contiguous True intervals in a 1D boolean array, merging tiny gaps."""
    idx = np.where(mask_1d)[0]
    if idx.size == 0:
        return []
    runs: list[tuple[int, int]] = []
    start = int(idx[0])
    prev = int(idx[0])
    for x in idx[1:]:
        ix = int(x)
        if ix - prev > min_gap:
            if prev - start + 1 >= min_len:
                runs.append((start, prev))
            start = ix
        prev = ix
    if prev - start + 1 >= min_len:
        runs.append((start, prev))
    return runs


def _recommend_chroma_key(rgb: np.ndarray, alpha_mask: np.ndarray) -> str:
    """Choose #00FF00 (green) for pink/red/purple subjects, or #FF00FF (magenta) if subject has green."""
    if not np.any(alpha_mask):
        return "#00FF00"
    fg = rgb[alpha_mask]
    r = fg[:, 0].astype(float)
    g = fg[:, 1].astype(float)
    b = fg[:, 2].astype(float)
    green_dominant = np.mean((g > r + 25) & (g > b + 25))
    if green_dominant > 0.08:
        return "#FF00FF"
    return "#00FF00"


def analyze_input_image(image_path: str | Path) -> dict[str, Any]:
    """Inspect an image file and determine its classification and metadata."""
    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return {
            "ok": False,
            "kind": "invalid",
            "error_code": "FILE_NOT_FOUND",
            "message_vi": f"Không tìm thấy file ảnh: {path.name}",
            "suggest_cutout": False,
        }

    try:
        with Image.open(path) as im:
            im_rgba = im.convert("RGBA")
            width, height = im_rgba.size
            arr = np.array(im_rgba)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        return {
            "ok": False,
            "kind": "invalid",
            "error_code": "CORRUPT_IMAGE",
            "message_vi": f"File ảnh bị hỏng hoặc sai định dạng ({exc}).",
            "suggest_cutout": False,
        }

    if width < 8 or height < 8:
        return {
            "ok": False,
            "kind": "invalid",
            "error_code": "TOO_SMALL",
            "message_vi": f"Kích thước ảnh quá nhỏ ({width}x{height} px).",
            "suggest_cutout": False,
        }

    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]
    opaque_mask = alpha > 16
    opaque_ratio = float(np.mean(opaque_mask))

    if opaque_ratio < 0.005:
        return {
            "ok": False,
            "kind": "invalid",
            "error_code": "EMPTY_ALPHA",
            "message_vi": "Ảnh hoàn toàn trong suốt (không có điểm ảnh nhân vật nào).",
            "suggest_cutout": False,
        }

    # Check if image has no alpha transparency (e.g. RGB JPEG or opaque background)
    corners = [arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]]
    corner_alphas = [int(c[3]) for c in corners]
    has_transparent_bg = min(corner_alphas) <= 16 and opaque_ratio < 0.92

    needs_cutout = False
    fg_mask = opaque_mask

    if not has_transparent_bg:
        return {
            "ok": False,
            "kind": "invalid",
            "error_code": "OPAQUE_WALL",
            "message_vi": (
                "Ảnh chưa được tách nền trong suốt (Alpha) hoặc là bản thiết kế nhân vật (Reference Sheet). "
                "Bạn có muốn chạy công cụ tách nền tự động (`sprite-gen cutout`) hoặc dùng ảnh này làm Reference cho AI vẽ Sprite không?"
            ),
            "suggest_cutout": True,
            "width": width,
            "height": height,
        }

    # Detect rows and columns of figures using 1D projections on fg_mask
    row_density = np.sum(fg_mask, axis=1)
    min_row_pixels = max(2, int(width * 0.004))
    row_runs = _find_1d_runs(row_density >= min_row_pixels, min_len=max(8, height // 25), min_gap=max(2, height // 80))

    total_cells = 0
    cols_per_row: list[int] = []
    for r0, r1 in row_runs:
        band = fg_mask[r0 : r1 + 1, :]
        col_density = np.sum(band, axis=0)
        min_col_pixels = max(2, int((r1 - r0 + 1) * 0.02))
        col_runs = _find_1d_runs(
            col_density >= min_col_pixels,
            min_len=max(6, width // 40),
            min_gap=max(2, width // 120),
        )
        if col_runs:
            cols_per_row.append(len(col_runs))
            total_cells += len(col_runs)

    rows_count = len(row_runs)
    max_cols = max(cols_per_row) if cols_per_row else 1

    # Decide classification
    if total_cells >= 2 and (max_cols >= 2 or rows_count >= 2):
        kind = "sprite_sheet"
    else:
        kind = "single_still"
        rows_count = max(1, rows_count)
        max_cols = 1
        total_cells = 1

    # Estimate cell dimensions and whether art style is pixel art vs HD smooth art
    est_cell_w = width // max(1, max_cols)
    est_cell_h = height // max(1, rows_count)
    render_mode = "pixel" if max(est_cell_w, est_cell_h) <= 128 else "smooth"
    recommended_chroma = _recommend_chroma_key(rgb, fg_mask)

    return {
        "ok": True,
        "kind": kind,
        "width": width,
        "height": height,
        "has_transparent_bg": has_transparent_bg,
        "needs_cutout": needs_cutout,
        "estimated_rows": rows_count,
        "estimated_cols": max_cols,
        "cols_per_row": cols_per_row,
        "estimated_frames": total_cells,
        "estimated_cell": [est_cell_w, est_cell_h],
        "recommended_chroma_key": recommended_chroma,
        "recommended_render_mode": render_mode,
        "message_vi": (
            f"Phát hiện Sprite Sheet ({rows_count} hàng, ~{total_cells} frames, ô ~{est_cell_w}x{est_cell_h} px)."
            if kind == "sprite_sheet"
            else f"Phát hiện Ảnh nhân vật tĩnh đơn lẻ ({width}x{height} px). Sẵn sàng tạo bộ chuyển động mới bằng AI."
        ),
    }
