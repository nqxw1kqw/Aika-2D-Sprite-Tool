/**
 * Main Application Controller (`app.js`) for Aika 2D Sprite Auto-Run Studio v2.0
 */
document.addEventListener("DOMContentLoaded", () => {
  const stagePlayer = new StagePlayer("stageCanvas");
  const codePanel = new CodePanel();
  const frameInspector = new FrameInspector(
    "framesTimeline",
    "analyzerSummaryText",
    handleInterpolate,
    handleManualFrameEdit
  );

  let currentProject = null;
  let systemStatus = null;

  // DOM Elements
  const projectSelect = document.getElementById("projectSelect");
  const runSelect = document.getElementById("runSelect");
  const skillSelect = document.getElementById("skillSelect");
  const promptInput = document.getElementById("promptInput");
  const inputList = document.getElementById("inputList");
  const stateSelect = document.getElementById("stateSelect");
  const progressBanner = document.getElementById("progressBanner");
  const progressStage = document.getElementById("progressStage");
  const progressText = document.getElementById("progressText");
  const progressBar = document.getElementById("progressBar");

  // Modal helpers
  const modalBackdrop = document.getElementById("modalBackdrop");
  const modalTitle = document.getElementById("modalTitle");
  const modalBody = document.getElementById("modalBody");
  document.getElementById("modalCloseBtn").onclick = () => modalBackdrop.classList.add("hidden");

  function showModal(title, htmlContent) {
    modalTitle.textContent = title;
    modalBody.innerHTML = htmlContent;
    modalBackdrop.classList.remove("hidden");
  }

  // 1. Connect SSE Progress Stream
  const evtSource = new EventSource("/api/events");
  evtSource.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      if (data.stage === "connected") return;
      progressBanner.classList.remove("hidden");
      progressStage.textContent = (data.stage || "WORK").toUpperCase();
      progressText.textContent = data.message || "";
      progressBar.style.width = `${data.progress || 0}%`;
      if (data.stage === "done" || data.progress >= 100) {
        setTimeout(() => progressBanner.classList.add("hidden"), 2500);
      }
    } catch (_) {}
  };

  // 2. Load System Status & Skills
  async function loadSystemStatus() {
    const res = await fetch("/api/status");
    systemStatus = await res.json();

    const codexBadge = document.getElementById("codexBadge");
    if (systemStatus.codex?.logged_in) {
      codexBadge.className = "sys-pill ok";
      codexBadge.textContent = "🤖 Codex CLI: Ready (ChatGPT OAuth)";
    } else {
      codexBadge.className = "sys-pill warn";
      codexBadge.textContent = "🤖 Codex CLI: Chưa đăng nhập";
    }

    const skills = systemStatus.skills || [];
    const skillBadge = document.getElementById("skillBadge");
    skillBadge.className = "sys-pill ok";
    skillBadge.textContent = `🪄 Skills: ${skills.length} đã cài đặt`;

    skillSelect.innerHTML = "";
    skills.forEach(s => {
      const opt = document.createElement("option");
      opt.value = s.id;
      opt.textContent = `${s.is_featured_2d ? "⭐ " : ""}${s.id} (${s.license})`;
      skillSelect.appendChild(opt);
    });
  }

  // 3. Load Projects List
  async function loadProjects(selectId = null) {
    const res = await fetch("/api/projects");
    const data = await res.json();
    const projects = data.projects || [];
    projectSelect.innerHTML = "";
    projects.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.name;
      projectSelect.appendChild(opt);
    });
    const targetId = selectId || (projects[0] && projects[0].id);
    if (targetId) {
      projectSelect.value = targetId;
      await selectProject(targetId);
    }
  }

  async function selectProject(projectId) {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}`);
    const proj = await res.json();
    if (!proj.ok) return;
    currentProject = proj;
    promptInput.value = proj.prompt || "";
    if (proj.default_skill) skillSelect.value = proj.default_skill;

    // Populate Runs dropdown
    runSelect.innerHTML = "";
    (proj.runs || []).forEach(r => {
      const opt = document.createElement("option");
      opt.value = r.id;
      const label =
        r.id === "codex_run"
          ? "🌟 codex_run (AI vẽ mới chuẩn 256×256)"
          : r.id === "unpacked_run"
          ? "🧪 unpacked_run (Ảnh gốc cắt tự động 110×160)"
          : `${r.id}${r.has_curation ? " (Đã Stabilize)" : ""}`;
      opt.textContent = label;
      if (r.id === proj.active_run) opt.selected = true;
      runSelect.appendChild(opt);
    });

    // Populate Inputs list
    inputList.innerHTML = "";
    (proj.inputs || []).forEach(inp => {
      const det = inp.detection || {};
      const card = document.createElement("div");
      card.className = `input-card ${inp.name === proj.active_input ? "active" : ""}`;
      let badgeHtml = `<span class="badge badge-err">Lỗi/Nền đặc</span>`;
      if (det.ok) {
        badgeHtml =
          det.kind === "sprite_sheet"
            ? `<span class="badge badge-sheet">Sprite Sheet (~${det.estimated_frames}f)</span>`
            : `<span class="badge badge-still">Ảnh tĩnh 1x1</span>`;
      }
      card.innerHTML = `
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:155px;" title="${det.message_vi || ""}">
          ${inp.name}
        </span>
        ${badgeHtml}
      `;
      card.onclick = () => {
        currentProject.active_input = inp.name;
        document.querySelectorAll(".input-card").forEach(c => c.classList.remove("active"));
        card.classList.add("active");
      };
      inputList.appendChild(card);
    });

    renderActiveRun(proj.run_detail);
  }

  function renderActiveRun(runDetail) {
    if (!runDetail || !runDetail.ok) return;
    const { manifest, analysis, atlas_url, previews, frame_urls, aseprite_url, manifest_url } = runDetail;

    // Populate State Selector
    const rows = manifest?.animation?.rows || {};
    const stateKeys = Object.keys(rows);
    stateSelect.innerHTML = "";
    stateKeys.forEach(st => {
      const opt = document.createElement("option");
      opt.value = st;
      opt.textContent = `${st} (${rows[st].frames} frames @ ${rows[st].fps} fps)`;
      stateSelect.appendChild(opt);
    });
    const defaultState = stateKeys.includes("walk") ? "walk" : stateKeys[0];
    stateSelect.value = defaultState;

    // Load Stage Player
    stagePlayer.loadRun(atlas_url, manifest, analysis);
    stagePlayer.setState(defaultState);

    // Load Frame Analyzer for current state
    const stAnalysis = analysis?.states?.[defaultState];
    frameInspector.renderStateAnalysis(defaultState, stAnalysis, frame_urls?.[defaultState] || []);

    // Populate Asset Download Links & GIF Previews
    const assetLinks = document.getElementById("assetLinks");
    assetLinks.innerHTML = `
      <a class="btn btn-sm btn-pink" href="${atlas_url}" download="sprite-sheet-alpha.png">🖼️ PNG Atlas</a>
      <a class="btn btn-sm" href="${manifest_url}" download="manifest.json">📄 manifest.json</a>
      ${aseprite_url ? `<a class="btn btn-sm" href="${aseprite_url}" download="aseprite.json">🎨 Aseprite JSON</a>` : ""}
    `;

    const gifGrid = document.getElementById("gifPreviewsGrid");
    gifGrid.innerHTML = "";
    Object.entries(previews || {}).forEach(([name, url]) => {
      const div = document.createElement("div");
      div.className = "gif-card";
      div.innerHTML = `
        <a href="${url}" download="${name}.gif" title="Bấm để tải ${name}.gif">
          <img src="${url}" class="${stagePlayer.pixelMode ? "pixelated" : ""}" alt="${name}" />
        </a>
        <span>${name}.gif</span>
      `;
      gifGrid.appendChild(div);
    });

    // Load Instant Code Preview
    codePanel.loadEngineCode(currentProject.id, runDetail.run_id, codePanel.currentEngine, stagePlayer.pixelMode);
  }

  // Event Listeners
  projectSelect.onchange = e => selectProject(e.target.value);

  runSelect.onchange = async e => {
    if (!currentProject) return;
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/select-run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: e.target.value }),
    });
    const proj = await res.json();
    if (proj.ok) {
      currentProject = proj;
      renderActiveRun(proj.run_detail);
    }
  };

  stateSelect.onchange = e => {
    const st = e.target.value;
    stagePlayer.setState(st);
    const rd = currentProject?.run_detail;
    if (rd) {
      frameInspector.renderStateAnalysis(st, rd.analysis?.states?.[st], rd.frame_urls?.[st] || []);
    }
  };

  // Stage Toolbar Controls
  const runModeBtn = document.getElementById("runModeBtn");
  runModeBtn.onclick = () => {
    stagePlayer.forwardMode = !stagePlayer.forwardMode;
    runModeBtn.textContent = stagePlayer.forwardMode ? "🏃 Chạy Tiến Tới (Forward Loop)" : "🧍 Đứng Tại Chỗ (In-Place)";
    runModeBtn.classList.toggle("btn-active", stagePlayer.forwardMode);
  };

  const pixelModeBtn = document.getElementById("pixelModeBtn");
  pixelModeBtn.onclick = () => {
    stagePlayer.pixelMode = !stagePlayer.pixelMode;
    frameInspector.pixelMode = stagePlayer.pixelMode;
    document.getElementById("stageCanvas").classList.toggle("pixelated", stagePlayer.pixelMode);
    pixelModeBtn.classList.toggle("btn-active", stagePlayer.pixelMode);
    if (currentProject?.run_detail) renderActiveRun(currentProject.run_detail);
  };

  const zoomBtn = document.getElementById("zoomBtn");
  zoomBtn.onclick = () => {
    const zooms = [1, 2, 3, 4];
    stagePlayer.zoom = zooms[(zooms.indexOf(stagePlayer.zoom) + 1) % zooms.length];
    zoomBtn.textContent = `🔍 Zoom: ${stagePlayer.zoom}x`;
  };

  const guidesBtn = document.getElementById("guidesBtn");
  guidesBtn.onclick = () => {
    stagePlayer.showGuides = !stagePlayer.showGuides;
    guidesBtn.classList.toggle("btn-active", stagePlayer.showGuides);
  };

  const fpsSlider = document.getElementById("fpsSlider");
  const fpsVal = document.getElementById("fpsVal");
  fpsSlider.oninput = e => {
    fpsVal.textContent = e.target.value;
    stagePlayer.fpsOverride = parseFloat(e.target.value);
  };

  document.getElementById("bgUploadInput").onchange = async e => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!currentProject) {
      stagePlayer.setCustomBackground(file);
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/background-tile`, {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    if (data.ok && data.tile_url) {
      stagePlayer.setCustomBackgroundUrl(data.tile_url + "?t=" + Date.now());
    } else {
      stagePlayer.setCustomBackground(file);
    }
  };

  // Drag & Drop + File Upload
  const dropZone = document.getElementById("dropZone");
  const fileUploadInput = document.getElementById("fileUploadInput");
  dropZone.onclick = () => fileUploadInput.click();
  dropZone.ondragover = e => { e.preventDefault(); dropZone.classList.add("dragover"); };
  dropZone.ondragleave = () => dropZone.classList.remove("dragover");
  dropZone.ondrop = e => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files?.[0]) uploadInputImage(e.dataTransfer.files[0]);
  };
  fileUploadInput.onchange = e => {
    if (e.target.files?.[0]) uploadInputImage(e.target.files[0]);
  };

  async function uploadInputImage(file) {
    if (!currentProject) return;
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/upload`, {
      method: "POST",
      body: fd,
    });
    const data = await res.json();
    if (data.ok) {
      await selectProject(currentProject.id);
    }
  }

  // WORK Buttons (Auto-Detect / Slice / AI Regen)
  function getSelectedStatesCsv() {
    const checked = Array.from(document.querySelectorAll(".state-chk:checked")).map(el => el.value);
    return checked.length > 0 ? checked.join(",") : "idle,walk";
  }

  async function executeWork(mode) {
    if (!currentProject) return;
    progressBanner.classList.remove("hidden");
    progressStage.textContent = mode.toUpperCase();
    progressText.textContent = "Đang khởi chạy nút ⚡ WORK...";
    progressBar.style.width = "15%";

    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/work`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        input_name: currentProject.active_input,
        prompt: promptInput.value,
        skill_id: skillSelect.value,
        states: getSelectedStatesCsv(),
        provider: "codex",
      }),
    });

    const data = await res.json();
    if (res.status === 422) {
      progressBanner.classList.add("hidden");
      const det = data.detail || {};
      showModal(
        "⚠️ Ảnh Đầu Vào Cần Xử Lý Trước",
        `<p>${det.message_vi || "Ảnh không hợp lệ."}</p>
         <div style="display:flex;gap:10px;margin-top:12px;">
           ${det.suggest_cutout ? `<button id="modalCutoutBtn" class="btn btn-pink">✂️ Chạy Tách Nền Tự Động (sprite-gen cutout)</button>` : ""}
           <button id="modalForceAiBtn" class="btn btn-active">🤖 Dùng Ảnh Này Làm Reference Để Codex Vẽ Sprite Mới</button>
         </div>`
      );
      const cutBtn = document.getElementById("modalCutoutBtn");
      if (cutBtn) cutBtn.onclick = () => { modalBackdrop.classList.add("hidden"); executeWork("cutout"); };
      const aiBtn = document.getElementById("modalForceAiBtn");
      if (aiBtn) aiBtn.onclick = () => { modalBackdrop.classList.add("hidden"); executeWork("ai_regen"); };
      return;
    }

    if (data.exit_code === 75 || data.error_code === "CODEX_UNAVAILABLE") {
      progressBanner.classList.add("hidden");
      showModal(
        "🛑 Codex CLI Cần Xác Nhận (Exit 75)",
        `<p>${data.message_vi}</p>
         <pre class="code-box" style="height:auto;">${JSON.stringify(data.ask || {}, null, 2)}</pre>`
      );
      return;
    }

    if (data.ok && data.project) {
      currentProject = data.project;
      await selectProject(currentProject.id);
    }
  }

  document.getElementById("workAutoBtn").onclick = () => executeWork("auto");
  document.getElementById("workSliceBtn").onclick = () => executeWork("slice");
  document.getElementById("workAiRegenBtn").onclick = () => executeWork("ai_regen");

  // 1-Click Auto-Stabilize & Reset Curation
  document.getElementById("stabilizeBtn").onclick = async () => {
    if (!currentProject) return;
    const enableBreathe = document.getElementById("breatheCheck").checked;
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/stabilize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: currentProject.active_run,
        drop_stalled: true,
        enable_idle_breathe: enableBreathe,
        breathe_mode: stagePlayer.pixelMode ? "pixel" : "smooth",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      await selectProject(currentProject.id);
    }
  };

  document.getElementById("resetCurationBtn").onclick = async () => {
    if (!currentProject?.active_run) return;
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/reset-curation`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: currentProject.active_run }),
    });
    const proj = await res.json();
    if (proj.ok) {
      currentProject = proj;
      renderActiveRun(proj.run_detail);
    }
  };

  async function handleInterpolate(stateName, fromIdx, toIdx) {
    if (!currentProject?.active_run) return;
    await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/interpolate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: currentProject.active_run,
        state: stateName,
        from_idx: fromIdx,
        to_idx: toIdx,
        provider: "codex",
      }),
    });
    await selectProject(currentProject.id);
  }

  async function handleManualFrameEdit(stateName, frameIdx, dx, dy, toggleSelected) {
    if (!currentProject?.active_run) return;
    const res = await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/frame-edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: currentProject.active_run,
        state: stateName,
        frame_index: frameIdx,
        delta_dx: dx,
        delta_dy: dy,
        toggle_selected: toggleSelected,
      }),
    });
    const data = await res.json();
    if (data.ok && data.project) {
      currentProject = data.project;
      renderActiveRun(currentProject.run_detail);
      stagePlayer.setState(stateName);
      stateSelect.value = stateName;
      const rd = currentProject.run_detail;
      frameInspector.renderStateAnalysis(stateName, rd.analysis?.states?.[stateName], rd.frame_urls?.[stateName] || []);
    }
  }

  document.getElementById("rerollStateBtn").onclick = async () => {
    if (!currentProject?.active_run) return;
    const st = stateSelect.value;
    await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/reroll-state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: currentProject.active_run,
        state: st,
        provider: "codex",
      }),
    });
    await selectProject(currentProject.id);
  };

  // Engine Code Tabs
  document.querySelectorAll(".eng-tab").forEach(btn => {
    btn.onclick = () => {
      document.querySelectorAll(".eng-tab").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      if (currentProject?.active_run) {
        codePanel.loadEngineCode(currentProject.id, currentProject.active_run, btn.dataset.engine, stagePlayer.pixelMode);
      }
    };
  });

  // AI Custom Code & Sandboxed Iframe Preview
  document.getElementById("genAiCodeBtn").onclick = async () => {
    if (!currentProject?.active_run) return;
    const prompt = document.getElementById("aiCodePrompt").value;
    await codePanel.generateAiSandboxCode(currentProject.id, currentProject.active_run, prompt, stagePlayer.pixelMode);
  };

  document.getElementById("runSandboxBtn").onclick = async () => {
    if (!currentProject?.active_run) return;
    if (!codePanel.lastSandboxHtml) {
      const prompt = document.getElementById("aiCodePrompt").value;
      await codePanel.generateAiSandboxCode(currentProject.id, currentProject.active_run, prompt, stagePlayer.pixelMode);
    }
    showModal(
      "🛡️ Chạy Thử Trong Sandbox Cô Lập (<iframe sandbox='allow-scripts'>)",
      `<p style="margin-top:0;font-size:12px;color:#9ca3af;">
         Môi trường cô lập an toàn: không có quyền <code>allow-same-origin</code>, không thể truy cập API máy chủ hay hệ thống file. Bấm vào khung bên dưới để điều khiển bằng phím <b>A/D, Space, J, K</b>!
       </p>
       <iframe id="sandboxFrame" class="sandbox-iframe" sandbox="allow-scripts"></iframe>`
    );
    const iframe = document.getElementById("sandboxFrame");
    iframe.srcdoc = codePanel.lastSandboxHtml;
  };

  // Read-only Skill Preview Modal
  document.getElementById("previewSkillBtn").onclick = async () => {
    const sid = skillSelect.value;
    const res = await fetch(`/api/skills/${encodeURIComponent(sid)}`);
    const data = await res.json();
    if (data.ok) {
      showModal(
        `📖 SKILL.md — ${data.skill.name} (${data.skill.license})`,
        `<p style="margin-top:0;font-size:11.5px;color:#9ca3af;">Đường dẫn gốc (Read-Only): <code>${data.skill.skill_md_path}</code></p>
         <pre class="code-box" style="height:360px;white-space:pre-wrap;">${data.preview.replace(/</g, "&lt;")}</pre>`
      );
    }
  };

  // New Project Button
  document.getElementById("newProjectBtn").onclick = async () => {
    const name = prompt("Nhập tên Project mới:", "New Sprite Project");
    if (!name) return;
    const res = await fetch("/api/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, prompt: promptInput.value, default_skill: skillSelect.value }),
    });
    const data = await res.json();
    if (data.ok) await loadProjects(data.id);
  };

  // Open in Antigravity IDE
  document.getElementById("openIdeBtn").onclick = async () => {
    if (!currentProject) return;
    await fetch(`/api/projects/${encodeURIComponent(currentProject.id)}/open-ide`, { method: "POST" });
  };

  // Boot Studio
  loadSystemStatus();
  loadProjects();
});
