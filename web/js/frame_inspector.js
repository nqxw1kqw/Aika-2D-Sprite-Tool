/**
 * Normalized Frame-by-Frame Inspector (`frame_inspector.js`)
 * Renders per-frame cards with Hair-Resistant Head Drift (%) and Normalized Leg Motion Ratio R_leg (%).
 */
class FrameInspector {
  constructor(containerId, summaryTextId, onInterpolateClick, onFrameEditClick) {
    this.container = document.getElementById(containerId);
    this.summaryText = document.getElementById(summaryTextId);
    this.onInterpolateClick = onInterpolateClick;
    this.onFrameEditClick = onFrameEditClick;
    this.pixelMode = false;
  }

  renderStateAnalysis(stateName, stateAnalysis, frameUrls = []) {
    this.container.innerHTML = "";
    if (!stateAnalysis || !stateAnalysis.ok) {
      this.summaryText.textContent = "Chưa có dữ liệu phân tích cho trạng thái này.";
      return;
    }

    const sum = stateAnalysis.summary || {};
    const statusText =
      sum.status === "NORMAL"
        ? "✅ ĐẠT CHUẨN (0 lỗi lệch đầu / giật nhịp)"
        : `⚠️ CẦN ỔN ĐỊNH: ${sum.head_drift_frames} frame lệch đầu, ${sum.stalled_frames} frame trùng, ${sum.jump_cut_frames} bước nhảy vọt`;

    this.summaryText.innerHTML = `<b>[${stateName.toUpperCase()}]</b> ${statusText} • Khung nhân vật: <code>${stateAnalysis.character_bbox?.width}×${stateAnalysis.character_bbox?.height} px</code>`;

    const frames = stateAnalysis.frames || [];
    frames.forEach((f, idx) => {
      const card = document.createElement("div");
      let statusCls = "status-ok";
      if (!f.selected) statusCls = "status-skip";
      else if (f.head_status !== "OK" || f.leg_status === "STALLED") statusCls = "status-err";
      else if (f.leg_status === "JUMP_CUT" || f.ground_status !== "OK") statusCls = "status-warn";

      card.className = `frame-card ${statusCls}`;
      const imgUrl = frameUrls[idx] || "";

      const headBadge =
        f.head_status === "OK"
          ? `<span style="color:#6ee7b7">Đầu: Δx=${f.head_dx_px}px (${f.head_drift_pct}%) ✓</span>`
          : `<span style="color:#fca5a5">Lắc đầu: Δx=${f.head_dx_px}px (${f.head_drift_pct}%) [bù dx=${f.recommended_dx > 0 ? "+" : ""}${f.recommended_dx}]</span>`;

      let legBadge = `<span style="color:#9ca3af">Nhịp chân: ${f.r_leg_pct}%</span>`;
      if (stateAnalysis.is_locomotion) {
        if (f.leg_status === "STALLED") {
          legBadge = `<span style="color:#fca5a5">Chân: ${f.r_leg_pct}% (&lt;5% Trùng!)</span>`;
        } else if (f.leg_status === "JUMP_CUT") {
          legBadge = `<span style="color:#fcd34d">Chân: ${f.r_leg_pct}% (&gt;35% Nhảy vọt)</span>`;
        } else {
          legBadge = `<span style="color:#6ee7b7">Chân: ${f.r_leg_pct}% (Đều 5–35%) ✓</span>`;
        }
      }

      card.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <b>Frame #${f.index}</b>
          <span class="badge ${f.selected ? (statusCls === "status-ok" ? "badge-sheet" : "badge-err") : "badge-warn"}">
            ${f.badges.join(" • ")}
          </span>
        </div>
        <div class="frame-thumb-wrap">
          ${imgUrl ? `<img src="${imgUrl}" class="${this.pixelMode ? "pixelated" : ""}" alt="frame-${f.index}" />` : ""}
        </div>
        <div class="frame-metrics">
          <div>${headBadge}</div>
          <div>${legBadge}</div>
          <div>Mặt đất: Δy=${f.baseline_dy_px}px</div>
        </div>
      `;

      if (this.onFrameEditClick) {
        const ctrlRow = document.createElement("div");
        ctrlRow.style.cssText = "display:flex;gap:3px;justify-content:space-between;margin-top:5px;";
        const mkBtn = (label, title, dx, dy, tog) => {
          const b = document.createElement("button");
          b.className = "btn btn-sm";
          b.style.padding = "2px 5px";
          b.style.fontSize = "10.5px";
          b.textContent = label;
          b.title = title;
          b.onclick = () => this.onFrameEditClick(stateName, f.index, dx, dy, tog);
          return b;
        };
        ctrlRow.appendChild(mkBtn("◀x", "Dịch trái 1px (dx - 1)", -1, 0, false));
        ctrlRow.appendChild(mkBtn("x▶", "Dịch phải 1px (dx + 1)", 1, 0, false));
        ctrlRow.appendChild(mkBtn("▲y", "Dịch lên 1px (dy - 1)", 0, -1, false));
        ctrlRow.appendChild(mkBtn("y▼", "Dịch xuống 1px (dy + 1)", 0, 1, false));
        ctrlRow.appendChild(mkBtn(f.selected ? "👁️" : "🚫", "Bật/Tắt sử dụng frame này trong vòng lặp", 0, 0, true));
        card.appendChild(ctrlRow);
      }

      if (f.selected && f.leg_status === "JUMP_CUT" && this.onInterpolateClick) {
        const interpBtn = document.createElement("button");
        interpBtn.className = "btn btn-sm";
        interpBtn.style.marginTop = "5px";
        interpBtn.textContent = `✨ Vẽ Bù Giữa #${f.index}→#${f.next_frame_index}`;
        interpBtn.onclick = () => this.onInterpolateClick(stateName, f.index, f.next_frame_index);
        card.appendChild(interpBtn);
      }

      this.container.appendChild(card);
    });
  }
}

window.FrameInspector = FrameInspector;
