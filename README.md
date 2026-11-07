# 🎨 Aika 2D Sprite Auto-Run Studio v2.0 (C++17 & DxLib + FastAPI Web Studio)

Bộ công cụ **2D Sprite Auto-Run Studio v2.0** kết hợp cả **Ứng dụng Desktop Native C++17 & DxLib (`.exe` 60FPS)** lẫn **Local Web Studio (`FastAPI + HTML5 Canvas`)** dành cho thiết kế, kiểm định, ổn định chuyển động và xuất mã nguồn 2D Sprite / Pixel Art đa nền tảng.

---

## ✨ Tính năng nổi bật

1. **Menu Hub 4 Tab trực quan trên bản C++17 & DxLib (`AikaSpriteStudioDxLib.exe`)**:
   - **Tab 1 — Sân Khấu & Frame (`Stage & Inspector`)**: Sân khấu DirectX 60FPS hỗ trợ **Forward Auto-Run** (sàn cuộn + bóng đổ động) & **In-Place Loop**, lọc **Crisp Pixel Art (`DX_DRAWMODE_NEAREST`)** / **Smooth HD (`DX_DRAWMODE_BILINEAR`)**, điều khiển nhân vật trực tiếp (`A/D`, `Space`, `J`) và tinh chỉnh pixel từng frame (`<x`, `x>`, `ON/OFF`).
   - **Tab 2 — Quản Lý & Nạp Ảnh (`Import & Detector Hub`)**: Mở hộp thoại chọn file chuẩn Windows (`GetOpenFileNameA`) hoặc kéo thả trực tiếp (`Drag & Drop`), tự động phân loại `sprite_sheet` vs `single_still`, cổng chặn lỗi nền đặc (`OPAQUE_WALL`) kèm nút **1-Click Tách Nền Trong Suốt (`Cutout`)**, **Auto-Slice 2s** và **Tạo Sàn Cuộn Vô Tận (`Seamless BG`)**.
   - **Tab 3 — Ổn Định & Thở (`Stabilizer & Curation Hub`)**: Chỉ số chuẩn hóa **Head Drift (`ΔX_head / W_char < 4%`)** & **Leg Motion (`5% <= R_leg <= 35%`)**, nút **1-Click Auto-Stabilize** khóa trục đầu + lọc frame khựng, lớp thở tự nhiên **Idle Breathe** (`Smooth` / `Pixel`), **Re-roll State** và **AI In-between Frame**.
   - **Tab 4 — Xuất Mã Nguồn & Tài Nguyên (`Export Hub`)**: Xuất code ăn liền 0 giây từ `manifest.json` cho **5 Engine**:
     - **C++ & DxLib (`dxlib_sprite_runner.cpp`)**
     - **HTML5 Canvas (`sprite_runner.html` — độc lập 1 file nhúng Base64)**
     - **Phaser 3 (`SpriteRunnerScene.js`)**
     - **Godot 4 (`SpriteRunner.gd`)**
     - **Unity C# (`SpriteAutoRunner.cs`)**

---

## 🚀 Cách chạy nhanh

### 1. Chạy bản Desktop Native C++17 & DxLib (`.exe`)
Nhấp đúp trực tiếp vào:
```powershell
.\AikaSpriteStudioDxLib.exe
```
Hoặc biên dịch lại từ mã nguồn `dxlib_app\main.cpp` (yêu cầu Visual Studio 2022 + `C:\DxLib_Normal`):
```powershell
.\dxlib_app\build_dxlib_exe.bat
```

### 2. Chạy bản Local Web Studio (`http://127.0.0.1:8780`)
```powershell
.\run_studio.bat
```

### 3. Chạy bộ kiểm thử tự động (`pytest`)
```powershell
.\.venv\bin\python.exe -m pytest tests/ -v
```
