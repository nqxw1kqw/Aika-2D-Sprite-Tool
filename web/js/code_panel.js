/**
 * 2-Tier Code Exporter & Sandboxed Preview Panel (`code_panel.js`)
 */
class CodePanel {
  constructor() {
    this.codeBox = document.getElementById("codePreviewBox");
    this.codeFilename = document.getElementById("codeFilename");
    this.copyBtn = document.getElementById("copyCodeBtn");
    this.downloadLink = document.getElementById("downloadCodeLink");
    this.currentEngine = "dxlib";
    this.currentCode = "";
    this.lastSandboxHtml = "";

    this.copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(this.currentCode || "");
      this.copyBtn.textContent = "✅ Đã Copy!";
      setTimeout(() => { this.copyBtn.textContent = "📋 Copy"; }, 1500);
    });
  }

  async loadEngineCode(projectId, runId, engine, pixelArt = false) {
    this.currentEngine = engine;
    if (!projectId || !runId) return;
    this.codeBox.textContent = "Đang sinh code tức thì (0s)...";
    const url = `/api/projects/${encodeURIComponent(projectId)}/export-code?engine=${encodeURIComponent(engine)}&run_id=${encodeURIComponent(runId)}&pixel_art=${pixelArt}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data.ok) {
      this.currentCode = data.code;
      this.codeFilename.textContent = data.filename;
      this.codeBox.textContent = data.code;
      this.downloadLink.href = data.download_url;
      this.downloadLink.download = data.filename;
    } else {
      this.codeBox.textContent = `Lỗi xuất code: ${data.detail || data.error}`;
    }
  }

  async generateAiSandboxCode(projectId, runId, prompt, pixelArt = false) {
    this.codeBox.textContent = "Đang sinh code gameplay tùy chỉnh...";
    const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/ai-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, prompt, pixel_art: pixelArt }),
    });
    const data = await res.json();
    if (data.ok) {
      this.currentCode = data.code;
      this.lastSandboxHtml = data.code;
      this.codeFilename.textContent = data.filename + " (Kiểm tra trước khi chạy)";
      this.codeBox.textContent = data.code;
      const blob = new Blob([data.code], { type: "text/html" });
      this.downloadLink.href = URL.createObjectURL(blob);
      this.downloadLink.download = data.filename;
    }
    return data;
  }
}

window.CodePanel = CodePanel;
