// Aika 2D Sprite Auto-Run Studio — Native C++17 & DxLib Desktop Application (.exe)
// Comprehensive User Menu Hub with 4 Modular Tabs:
// Tab 0: Stage & Frame Inspector (60FPS DirectX Stage, Jump, Heart Shot, Frame Nudge, Metrics)
// Tab 1: Image & Import Hub (Browse Windows File Dialog, Drag & Drop, Auto-Detector, 1-Click Cutout, Auto-Slice, Seamless BG)
// Tab 2: Stabilizer & Curation Hub (1-Click Auto-Stabilize, Idle Breathe Layer, In-between Interpolation, Re-roll State)
// Tab 3: Code & Asset Export Hub (C++ DxLib, HTML5 Canvas, Phaser 3, Godot 4, Unity C#, Asset Bundle, Open Folders)

#define _CRT_SECURE_NO_WARNINGS
#define NOMINMAX
#include "DxLib.h"
#include <windows.h>
#include <commdlg.h>
#include <shellapi.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

struct FrameInfo {
    int index = 0;
    int rx = 0, ry = 0, rw = 256, rh = 256;
    bool selected = true;
    int curDx = 0;
    int curDy = 0;
    float headX = 128.0f;
    float headDx = 0.0f;
    float headPct = 0.0f;
    float rLegPct = 0.0f;
    std::string headStatus = "OK";
    std::string legStatus = "NORMAL";
};

struct StateData {
    std::string name;
    float fps = 8.0f;
    bool loop = true;
    std::string status = "NORMAL";
    int headDriftCount = 0;
    int stalledCount = 0;
    int jumpCutCount = 0;
    int charW = 256;
    int charH = 256;
    std::vector<FrameInfo> frames;
};

struct ButtonRect {
    int x, y, w, h;
    std::string label;
    std::string id;
    unsigned int bgCol;
    unsigned int textCol;
    bool active = false;

    bool contains(int mx, int my) const {
        return mx >= x && mx <= x + w && my >= y && my <= y + h;
    }
};

struct HeartShot {
    float x, y, vx;
    int life;
};

struct DetectorInfo {
    bool ok = true;
    std::string kind = "sprite_sheet";
    int width = 0;
    int height = 0;
    int rows = 1;
    int cols = 1;
    bool hasAlpha = true;
    std::string chromaKey = "#00FF00";
    std::string errorCode = "NONE";
    std::string message = "Ready for pipeline";
};

// Global Studio State
static std::string g_projectId = "jirai-neko-demo";
static std::string g_activeRun = "codex_run";
static std::vector<std::string> g_availableRuns;
static std::string g_activeInput = "input_sheet.png";
static std::vector<std::string> g_availableInputs;
static std::string g_inputPath;
static int g_inputThumbHandle = -1;
static DetectorInfo g_detector;

static std::string g_atlasPath;
static int g_atlasHandle = -1;
static std::vector<std::string> g_stateOrder;
static std::map<std::string, StateData> g_states;
static std::string g_currentState = "walk";

static std::atomic<bool> g_isWorking(false);
static std::atomic<bool> g_needsReload(false);
static std::string g_statusBanner = "San sang - Hay chon anh hoac keo tha file vao day nhe!";
static int g_activeTab = 0; // 0: Stage, 1: Import Hub, 2: Stabilize, 3: Export
static std::string g_breatheMode = "smooth";

// Windows File Open Dialog
static std::string openImageFileDialog() {
    char filename[MAX_PATH] = {0};
    OPENFILENAMEA ofn = {0};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = GetMainWindowHandle();
    ofn.lpstrFilter = "Image Files (*.png;*.jpg;*.jpeg;*.webp)\0*.png;*.jpg;*.jpeg;*.webp\0All Files (*.*)\0*.*\0";
    ofn.lpstrFile = filename;
    ofn.nMaxFile = MAX_PATH;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    ofn.lpstrTitle = "Chon file anh Sprite Sheet hoac Nhan vat (PNG / JPG / WEBP)";

    if (GetOpenFileNameA(&ofn)) {
        return std::string(filename);
    }
    return "";
}

static bool loadMetaFile(const std::string& metaPath) {
    std::ifstream in(metaPath);
    if (!in.is_open()) return false;

    g_availableRuns.clear();
    g_availableInputs.clear();
    g_stateOrder.clear();
    g_states.clear();

    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::istringstream iss(line);
        std::string tag;
        iss >> tag;
        if (tag == "PROJECT") {
            std::string runsCsv;
            iss >> g_projectId >> g_activeRun >> runsCsv;
            std::istringstream rss(runsCsv);
            std::string rItem;
            while (std::getline(rss, rItem, ',')) {
                if (!rItem.empty()) g_availableRuns.push_back(rItem);
            }
        } else if (tag == "INPUTS") {
            std::string inputsCsv;
            iss >> g_activeInput >> inputsCsv;
            std::istringstream issInputs(inputsCsv);
            std::string inItem;
            while (std::getline(issInputs, inItem, ',')) {
                if (!inItem.empty()) g_availableInputs.push_back(inItem);
            }
        } else if (tag == "INPUT_PATH") {
            std::getline(iss >> std::ws, g_inputPath);
        } else if (tag == "DETECT") {
            int okFlag = 1, alphaFlag = 1;
            iss >> okFlag >> g_detector.kind >> g_detector.width >> g_detector.height
                >> g_detector.rows >> g_detector.cols >> alphaFlag
                >> g_detector.chromaKey >> g_detector.errorCode;
            g_detector.ok = (okFlag != 0);
            g_detector.hasAlpha = (alphaFlag != 0);
        } else if (tag == "DETECT_MSG") {
            std::getline(iss >> std::ws, g_detector.message);
        } else if (tag == "ATLAS") {
            std::getline(iss >> std::ws, g_atlasPath);
        } else if (tag == "STATE") {
            StateData sd;
            int loopFlag = 1;
            iss >> sd.name >> sd.fps >> loopFlag >> sd.status
                >> sd.headDriftCount >> sd.stalledCount >> sd.jumpCutCount
                >> sd.charW >> sd.charH;
            sd.loop = (loopFlag != 0);
            g_stateOrder.push_back(sd.name);
            g_states[sd.name] = sd;
        } else if (tag == "FRAME") {
            std::string stName;
            FrameInfo fi;
            int selFlag = 1;
            iss >> stName >> fi.index >> fi.rx >> fi.ry >> fi.rw >> fi.rh
                >> selFlag >> fi.curDx >> fi.curDy >> fi.headX >> fi.headDx
                >> fi.headPct >> fi.rLegPct >> fi.headStatus >> fi.legStatus;
            fi.selected = (selFlag != 0);
            g_states[stName].frames.push_back(fi);
        }
    }

    if (g_atlasHandle != -1) {
        DeleteGraph(g_atlasHandle);
        g_atlasHandle = -1;
    }
    if (!g_atlasPath.empty()) {
        g_atlasHandle = LoadGraph(g_atlasPath.c_str());
    }
    if (g_inputThumbHandle != -1) {
        DeleteGraph(g_inputThumbHandle);
        g_inputThumbHandle = -1;
    }
    if (!g_inputPath.empty()) {
        g_inputThumbHandle = LoadGraph(g_inputPath.c_str());
    }

    if (g_states.find(g_currentState) == g_states.end() && !g_stateOrder.empty()) {
        g_currentState = g_states.count("walk") ? "walk" : g_stateOrder[0];
    }
    return true;
}

static void runPythonBridgeAsync(const std::string& args, const std::string& workingMsg, const std::string& doneMsg) {
    if (g_isWorking.load()) return;
    g_isWorking.store(true);
    g_statusBanner = workingMsg;

    std::thread([args, doneMsg]() {
        std::string cmd = "\".venv\\bin\\python.exe\" app\\dxlib_cli_bridge.py " + args;
        STARTUPINFOA si = { sizeof(si) };
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        PROCESS_INFORMATION pi = {};
        std::vector<char> cmdBuf(cmd.begin(), cmd.end());
        cmdBuf.push_back('\0');

        if (CreateProcessA(NULL, cmdBuf.data(), NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
            WaitForSingleObject(pi.hProcess, INFINITE);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
        }
        g_statusBanner = doneMsg;
        g_needsReload.store(true);
        g_isWorking.store(false);
    }).detach();
}

static void drawRoundedPanel(int x, int y, int w, int h, unsigned int fillCol, unsigned int borderCol) {
    DrawBox(x, y, x + w, y + h, fillCol, TRUE);
    DrawBox(x, y, x + w, y + h, borderCol, FALSE);
}

int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {
    char exePath[MAX_PATH] = {0};
    if (GetModuleFileNameA(NULL, exePath, MAX_PATH) > 0) {
        std::string dir(exePath);
        size_t pos = dir.find_last_of("\\/");
        if (pos != std::string::npos) {
            SetCurrentDirectoryA(dir.substr(0, pos).c_str());
        }
    }

    SetOutApplicationLogValidFlag(FALSE);
    ChangeWindowMode(TRUE);
    SetGraphMode(1280, 720, 32);
    SetWindowSizeChangeEnableFlag(TRUE);
    SetAlwaysRunFlag(TRUE);
    SetDragFileValidFlag(TRUE);
    SetMainWindowText("Aika 2D Sprite Auto-Run Studio v2.0 [DxLib C++ Desktop Edition]");

    if (DxLib_Init() == -1) return -1;
    SetDrawScreen(DX_SCREEN_BACK);
    HWND hwnd = GetMainWindowHandle();
    ShowWindow(hwnd, SW_SHOWNORMAL);
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);
    SetForegroundWindow(hwnd);
    SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW);

    int fontTitle = CreateFontToHandle("Segoe UI", 18, 7, DX_FONTTYPE_ANTIALIASING_4X4);
    int fontTab   = CreateFontToHandle("Segoe UI", 14, 6, DX_FONTTYPE_ANTIALIASING_4X4);
    int fontBold  = CreateFontToHandle("Segoe UI", 14, 6, DX_FONTTYPE_ANTIALIASING_4X4);
    int fontSmall = CreateFontToHandle("Consolas", 12, 4, DX_FONTTYPE_ANTIALIASING_4X4);

    if (GetFileAttributesA("dxlib_meta.txt") == INVALID_FILE_ATTRIBUTES) {
        system("\".venv\\bin\\python.exe\" app\\dxlib_cli_bridge.py sync --run codex_run");
    }
    loadMetaFile("dxlib_meta.txt");

    bool forwardLoop = true;
    bool pixelMode = false;
    bool showGuides = true;
    int zoom = 1;
    int animCursor = 0;
    int lastFrameTick = GetNowCount();

    float scrollX = 0.0f;
    float actorY = 0.0f;
    float vy = 0.0f;
    bool flipX = false;
    std::vector<HeartShot> hearts;

    int prevMouse = 0;
    int prevSpace = 0;
    int prevJ = 0;

    unsigned int colBg      = GetColor(14, 16, 23);
    unsigned int colPanel   = GetColor(22, 25, 37);
    unsigned int colCard    = GetColor(31, 36, 54);
    unsigned int colBorder  = GetColor(46, 53, 80);
    unsigned int colPink    = GetColor(236, 72, 153);
    unsigned int colViolet  = GetColor(139, 92, 246);
    unsigned int colGreen   = GetColor(16, 185, 129);
    unsigned int colAmber   = GetColor(245, 158, 11);
    unsigned int colRed     = GetColor(239, 68, 68);
    unsigned int colWhite   = GetColor(243, 244, 246);
    unsigned int colMuted   = GetColor(156, 163, 175);
    unsigned int colCyan    = GetColor(6, 182, 212);

    while (ProcessMessage() == 0 && CheckHitKey(KEY_INPUT_ESCAPE) == 0) {
        if (g_needsReload.exchange(false)) {
            loadMetaFile("dxlib_meta.txt");
            animCursor = 0;
        }

        // Handle Drag & Drop anywhere in the window
        if (GetDragFileNum() > 0) {
            char droppedPath[MAX_PATH] = {0};
            if (GetDragFilePath(droppedPath) == 0) {
                DragFileInfoClear();
                runPythonBridgeAsync(
                    std::string("drop --file \"") + droppedPath + "\"",
                    std::string("Dang tu dong phan tich & nhap anh: ") + droppedPath,
                    "Anh moi da duoc nap thanh cong vao Studio!"
                );
            }
        }

        int mx = 0, my = 0;
        GetMousePoint(&mx, &my);
        int mouseNow = GetMouseInput();
        bool clicked = ((mouseNow & MOUSE_INPUT_LEFT) != 0) && ((prevMouse & MOUSE_INPUT_LEFT) == 0);
        prevMouse = mouseNow;

        ClearDrawScreen();
        DrawBox(0, 0, 1280, 720, colBg, TRUE);

        std::vector<ButtonRect> buttons;

        // 1. TOP HEADER BAR WITH MENU HUB TABS
        drawRoundedPanel(0, 0, 1280, 52, GetColor(18, 21, 32), colBorder);
        DrawStringToHandle(14, 14, "AIKA 2D SPRITE STUDIO", colPink, fontTitle);

        // 4 Main Navigation Tabs
        struct TabDef { int id; std::string label; int x, w; };
        std::vector<TabDef> tabs = {
            { 0, "1. SAN KHAU & FRAME", 280, 190 },
            { 1, "2. QUAN LY & NAP ANH", 480, 190 },
            { 2, "3. ON DINH & THO",    680, 180 },
            { 3, "4. XUAT CODE & ENGINE", 870, 190 },
        };
        for (const auto& t : tabs) {
            bool isActive = (g_activeTab == t.id);
            unsigned int tabBg = isActive ? colPink : colCard;
            unsigned int tabText = isActive ? colWhite : colMuted;
            buttons.push_back({ t.x, 8, t.w, 36, t.label, "tab_" + std::to_string(t.id), tabBg, tabText, isActive });
        }

        // Status Banner right aligned
        DrawStringToHandle(1070, 17, g_statusBanner.c_str(), g_isWorking.load() ? colAmber : colGreen, fontSmall);

        // TAB 0: STAGE & FRAME INSPECTOR (MAIN DASHBOARD)
        if (g_activeTab == 0) {
            // Left Quick Panel
            drawRoundedPanel(12, 60, 276, 648, colPanel, colBorder);
            DrawStringToHandle(22, 70, "DIEU KHIEN CHUYEN DONG", colPink, fontBold);
            DrawFormatStringToHandle(22, 94, colWhite, fontSmall, "Run: %s", g_activeRun.c_str());
            DrawFormatStringToHandle(22, 112, colMuted, fontSmall, "Input: %s", g_activeInput.c_str());

            buttons.push_back({ 22, 134, 256, 32, "Chon anh tu may...", "quick_browse", colCyan, colWhite });
            buttons.push_back({ 22, 172, 256, 34, "Doi Run (codex / unpacked)", "switch_run", colCard, colWhite });
            buttons.push_back({ 22, 212, 256, 36, "⚡ 1-Click Auto-Stabilize", "stabilize", colViolet, colWhite });
            buttons.push_back({ 22, 254, 256, 34, "Khoi phuc goc (Reset)", "reset", colCard, colWhite });

            DrawStringToHandle(22, 302, "TOC DO & TRANG THAI", colPink, fontBold);
            const StateData& curSt = g_states[g_currentState];
            DrawFormatStringToHandle(22, 326, colWhite, fontSmall, "State: %s (FPS: %.1f)", g_currentState.c_str(), curSt.fps);
            buttons.push_back({ 22, 346, 124, 28, "FPS -1", "fps_dec", colCard, colWhite });
            buttons.push_back({ 154, 346, 124, 28, "FPS +1", "fps_inc", colCard, colWhite });

            DrawStringToHandle(22, 388, "PHIM TAT TRONG SAN KHAU", colPink, fontBold);
            DrawStringToHandle(22, 410, "A / D : Chay qua lai & Lat mat", colMuted, fontSmall);
            DrawStringToHandle(22, 428, "SPACE : Nhay len cao", colMuted, fontSmall);
            DrawStringToHandle(22, 446, "J     : Ban tim hong", colMuted, fontSmall);
            DrawStringToHandle(22, 464, "ESC   : Thoat Studio", colMuted, fontSmall);

            // Drag & Drop box
            drawRoundedPanel(22, 494, 256, 202, GetColor(18, 20, 30), colPink);
            DrawStringToHandle(36, 510, "KEO THA ANH VAO DAY", colPink, fontBold);
            DrawStringToHandle(30, 536, "- Tha Sprite Sheet: Tu dong cat", colMuted, fontSmall);
            DrawStringToHandle(30, 554, "- Tha 1 Anh tinh: Goi AI tao bo", colMuted, fontSmall);
            DrawStringToHandle(30, 572, "- Ho tro: PNG, JPG, WEBP", colMuted, fontSmall);
            buttons.push_back({ 36, 600, 228, 36, "🚀 Xuat C++ DxLib / Web / Unity", "export_code", colGreen, colWhite });
            buttons.push_back({ 36, 646, 228, 34, "🌐 Mo Web Studio (8780)", "open_web", colCard, colWhite });

            // Center Top: Stage (976 x 388)
            int stX = 296, stY = 60, stW = 972, stH = 390;
            drawRoundedPanel(stX, stY, stW, stH, GetColor(16, 18, 28), colBorder);

            // Stage Toolbar
            int tx = stX + 10;
            for (const auto& sname : g_stateOrder) {
                bool isCur = (sname == g_currentState);
                buttons.push_back({ tx, stY + 8, 86, 28, sname, "state_" + sname, isCur ? colPink : colCard, colWhite, isCur });
                tx += 92;
            }
            buttons.push_back({ stX + 410, stY + 8, 170, 28, forwardLoop ? "Mode: Auto-Run Cuon" : "Mode: Loop Tai Cho", "toggle_forward", forwardLoop ? colPink : colCard, colWhite });
            buttons.push_back({ stX + 588, stY + 8, 145, 28, pixelMode ? "Filter: Pixel Sac Net" : "Filter: Smooth HD", "toggle_pixel", pixelMode ? colViolet : colCard, colWhite });
            buttons.push_back({ stX + 740, stY + 8, 95, 28, "Zoom: " + std::to_string(zoom) + "x", "toggle_zoom", colCard, colWhite });
            buttons.push_back({ stX + 842, stY + 8, 118, 28, showGuides ? "Can truc: BAT" : "Can truc: TAT", "toggle_guides", showGuides ? colGreen : colCard, colWhite });

            // Animation timing & Input handling
            std::vector<int> activeIndices;
            for (size_t i = 0; i < curSt.frames.size(); ++i) {
                if (curSt.frames[i].selected) activeIndices.push_back((int)i);
            }
            if (activeIndices.empty() && !curSt.frames.empty()) activeIndices.push_back(0);

            int now = GetNowCount();
            int frameInterval = (int)(1000.0f / std::max(1.0f, curSt.fps));
            if (!activeIndices.empty() && now - lastFrameTick >= frameInterval) {
                animCursor = (animCursor + 1) % (int)activeIndices.size();
                lastFrameTick = now;
            }

            if (CheckHitKey(KEY_INPUT_RIGHT) || CheckHitKey(KEY_INPUT_D)) {
                flipX = false; scrollX += 4.5f;
            } else if (CheckHitKey(KEY_INPUT_LEFT) || CheckHitKey(KEY_INPUT_A)) {
                flipX = true; scrollX -= 4.5f;
            } else if (forwardLoop) {
                scrollX += 3.0f;
            }

            int spaceNow = CheckHitKey(KEY_INPUT_SPACE);
            if (spaceNow && !prevSpace && actorY == 0.0f) vy = -11.0f;
            prevSpace = spaceNow;

            if (actorY < 0.0f || vy < 0.0f) {
                actorY += vy; vy += 0.58f;
                if (actorY >= 0.0f) { actorY = 0.0f; vy = 0.0f; }
            }

            int jNow = CheckHitKey(KEY_INPUT_J);
            if (jNow && !prevJ) {
                hearts.push_back({ (float)(stX + stW / 2 + (flipX ? -40 : 40)), (float)(stY + 260 + (int)actorY), flipX ? -8.5f : 8.5f, 75 });
            }
            prevJ = jNow;

            // Ground & Ruler
            int groundY = stY + stH - 42;
            DrawLine(stX + 16, groundY, stX + stW - 16, groundY, GetColor(95, 102, 145), 2);
            int tickOff = ((int)scrollX % 64 + 64) % 64;
            for (int rx = stX + 24 - tickOff; rx < stX + stW - 20; rx += 64) {
                if (rx >= stX + 16) DrawLine(rx, groundY, rx, groundY + 10, GetColor(75, 82, 118), 2);
            }

            // Draw Sprite
            if (g_atlasHandle != -1 && !activeIndices.empty()) {
                int fIdx = activeIndices[animCursor % activeIndices.size()];
                const FrameInfo& fi = curSt.frames[fIdx];
                int subH = DerivationGraph(fi.rx, fi.ry, fi.rw, fi.rh, g_atlasHandle);

                float baseScale = (fi.rh > 210) ? (220.0f / (float)fi.rh) : 1.25f;
                float scale = pixelMode ? (float)zoom : (baseScale * (float)zoom * 0.88f);
                int drawW = (int)std::round(fi.rw * scale);
                int drawH = (int)std::round(fi.rh * scale);
                int cx = stX + stW / 2;
                int topY = groundY - drawH + (int)actorY;

                // Dynamic Shadow
                SetDrawBlendMode(DX_BLENDMODE_ALPHA, 135);
                DrawOval(cx, groundY - 2, std::max(20, (int)(drawW * 0.22f)), 7, GetColor(8, 8, 16), TRUE);
                SetDrawBlendMode(DX_BLENDMODE_NOBLEND, 0);

                SetDrawMode(pixelMode ? DX_DRAWMODE_NEAREST : DX_DRAWMODE_BILINEAR);
                if (!flipX) DrawExtendGraph(cx - drawW / 2, topY, cx + drawW / 2, topY + drawH, subH, TRUE);
                else DrawExtendGraph(cx + drawW / 2, topY, cx - drawW / 2, topY + drawH, subH, TRUE);
                SetDrawMode(DX_DRAWMODE_BILINEAR);
                DeleteGraph(subH);

                if (showGuides && !curSt.frames.empty()) {
                    const FrameInfo& refFi = curSt.frames[0];
                    int refScreenX = cx - drawW / 2 + (int)((refFi.headX / std::max(1, fi.rw)) * drawW);
                    int curScreenX = cx - drawW / 2 + (int)((fi.headX / std::max(1, fi.rw)) * drawW);
                    DrawLine(refScreenX, topY + 6, refScreenX, groundY, colGreen, 1);
                    if (std::fabs(fi.headDx) > 1.0f) DrawLine(curScreenX, topY + 6, curScreenX, topY + drawH / 2, colRed, 2);
                }

                DrawFormatStringToHandle(stX + 18, stY + 46, colWhite, fontSmall,
                    "Run: %s | State: %s | Frame #%d (%d/%d) | Cell: %dx%dpx | Head dx: %.1fpx (%.1f%%) | Leg: %.1f%% [%s]",
                    g_activeRun.c_str(), g_currentState.c_str(), fi.index, animCursor + 1, (int)activeIndices.size(),
                    fi.rw, fi.rh, fi.headDx, fi.headPct, fi.rLegPct, fi.legStatus.c_str());
            }

            // Hearts
            for (int i = (int)hearts.size() - 1; i >= 0; --i) {
                hearts[i].x += hearts[i].vx;
                hearts[i].life--;
                DrawCircle((int)hearts[i].x, (int)hearts[i].y, 7, colPink, TRUE);
                DrawCircle((int)hearts[i].x, (int)hearts[i].y, 9, colWhite, FALSE);
                if (hearts[i].life <= 0 || hearts[i].x < stX || hearts[i].x > stX + stW) hearts.erase(hearts.begin() + i);
            }

            // Bottom Panel: Normalized Frame Inspector (972 x 250)
            int anX = 296, anY = 458, anW = 972, anH = 250;
            drawRoundedPanel(anX, anY, anW, anH, colPanel, colBorder);
            unsigned int sumCol = (curSt.status == "NORMAL") ? colGreen : colRed;
            DrawFormatStringToHandle(anX + 14, anY + 10, sumCol, fontBold,
                "BANG PHAN TICH CHUAN HOA [%s] -> Trang thai: %s (Lech dau: %d, Khung khung <5%%: %d, Nhay goc >35%%: %d)",
                g_currentState.c_str(), curSt.status.c_str(), curSt.headDriftCount, curSt.stalledCount, curSt.jumpCutCount);

            int cardW = 114, cardGap = 6, startX = anX + 12, cardY = anY + 36, cardH = 202;
            for (size_t i = 0; i < curSt.frames.size() && i < 8; ++i) {
                const FrameInfo& fi = curSt.frames[i];
                int cx = startX + (int)i * (cardW + cardGap);
                unsigned int bCol = colGreen;
                if (!fi.selected) bCol = colMuted;
                else if (fi.headStatus != "OK" || fi.legStatus == "STALLED") bCol = colRed;
                else if (fi.legStatus == "JUMP_CUT") bCol = colAmber;

                drawRoundedPanel(cx, cardY, cardW, cardH, colCard, bCol);
                DrawFormatStringToHandle(cx + 6, cardY + 5, colWhite, fontSmall, "Frame #%d %s", fi.index, fi.selected ? "" : "[SKIP]");

                if (g_atlasHandle != -1) {
                    int thumbH = DerivationGraph(fi.rx, fi.ry, fi.rw, fi.rh, g_atlasHandle);
                    DrawBox(cx + 8, cardY + 24, cx + cardW - 8, cardY + 102, GetColor(18, 20, 30), TRUE);
                    SetDrawMode(pixelMode ? DX_DRAWMODE_NEAREST : DX_DRAWMODE_BILINEAR);
                    DrawExtendGraph(cx + 18, cardY + 26, cx + cardW - 18, cardY + 100, thumbH, TRUE);
                    DeleteGraph(thumbH);
                }

                DrawFormatStringToHandle(cx + 6, cardY + 106, (fi.headStatus == "OK") ? colGreen : colRed, fontSmall, "Head: %.1f%%", fi.headPct);
                DrawFormatStringToHandle(cx + 6, cardY + 124, (fi.legStatus == "NORMAL") ? colGreen : colAmber, fontSmall, "Leg: %.1f%%", fi.rLegPct);
                DrawFormatStringToHandle(cx + 6, cardY + 142, colMuted, fontSmall, "%s", fi.legStatus.c_str());

                std::string prefix = "f_" + std::to_string(fi.index) + "_";
                buttons.push_back({ cx + 6, cardY + 164, 30, 24, "<x", prefix + "dx_neg", GetColor(45, 52, 75), colWhite });
                buttons.push_back({ cx + 40, cardY + 164, 30, 24, "x>", prefix + "dx_pos", GetColor(45, 52, 75), colWhite });
                buttons.push_back({ cx + 74, cardY + 164, 34, 24, fi.selected ? "ON" : "OFF", prefix + "tog", fi.selected ? colGreen : colRed, colWhite });
            }
        }

        // TAB 1: IMAGE & IMPORT HUB (FULL DETECTOR & FILE MANAGER)
        else if (g_activeTab == 1) {
            // Left Column: Inputs List & File Dialog (420px)
            drawRoundedPanel(12, 60, 420, 648, colPanel, colBorder);
            DrawStringToHandle(24, 72, "DANH SACH ANH VAO (INPUTS)", colPink, fontBold);
            buttons.push_back({ 24, 98, 396, 42, "📂 DUYET FILE ANH TU MAY TINH (PNG/JPG)...", "dlg_import", colPink, colWhite });

            DrawStringToHandle(24, 154, "Chon anh trong thu muc inputs/:", colWhite, fontSmall);
            int inY = 176;
            for (const auto& inp : g_availableInputs) {
                bool isAct = (inp == g_activeInput);
                buttons.push_back({ 24, inY, 396, 32, (isAct ? "> " : "  ") + inp, "sel_inp_" + inp, isAct ? colViolet : colCard, colWhite, isAct });
                inY += 38;
            }

            // Drag Drop area
            drawRoundedPanel(24, 460, 396, 236, GetColor(18, 20, 30), colPink);
            DrawStringToHandle(36, 478, "HOAC KEO THA FILE VAO DAY", colPink, fontBold);
            DrawStringToHandle(36, 510, "- Keo truc tiep tu Windows Explorer vao cua so nay", colMuted, fontSmall);
            DrawStringToHandle(36, 530, "- He thong se tu copy vao inputs/ va kiem dinh", colMuted, fontSmall);
            DrawStringToHandle(36, 550, "- Ho tro: PNG (Alpha), JPG (Reference Sheet), WEBP", colMuted, fontSmall);
            DrawStringToHandle(36, 580, "Trang thai hien tai:", colWhite, fontSmall);
            DrawFormatStringToHandle(36, 602, colGreen, fontSmall, "Active Input: %s", g_activeInput.c_str());
            DrawFormatStringToHandle(36, 622, colCyan, fontSmall, "File path: %s", g_inputPath.c_str());

            // Right Column: Auto-Detector Inspection & Actions (832px)
            int rX = 444, rY = 60, rW = 824, rH = 648;
            drawRoundedPanel(rX, rY, rW, rH, colPanel, colBorder);
            DrawStringToHandle(rX + 18, rY + 14, "KET QUA KIEM DINH ANH (AUTO-DETECTOR REPORT)", colPink, fontBold);

            // Preview Thumbnail Box
            drawRoundedPanel(rX + 18, rY + 44, 260, 260, GetColor(16, 18, 28), colBorder);
            if (g_inputThumbHandle != -1) {
                DrawExtendGraph(rX + 22, rY + 48, rX + 274, rY + 300, g_inputThumbHandle, TRUE);
            } else {
                DrawStringToHandle(rX + 60, rY + 160, "[ Khong co anh xem truoc ]", colMuted, fontSmall);
            }

            // Detector Properties
            int infoX = rX + 296, infoY = rY + 48;
            DrawFormatStringToHandle(infoX, infoY, colWhite, fontBold, "Ten file: %s", g_activeInput.c_str());
            DrawFormatStringToHandle(infoX, infoY + 28, colCyan, fontSmall, "Phan loai: %s (%s)",
                g_detector.kind.c_str(),
                (g_detector.kind == "sprite_sheet") ? "Sprite Sheet nhieu frame" : "Anh tinh 1 nhan vat");
            DrawFormatStringToHandle(infoX, infoY + 50, colWhite, fontSmall, "Kich thuoc: %d x %d px", g_detector.width, g_detector.height);
            DrawFormatStringToHandle(infoX, infoY + 72, colWhite, fontSmall, "Uoc tinh grid: %d hang x %d cot", g_detector.rows, g_detector.cols);
            DrawFormatStringToHandle(infoX, infoY + 94, g_detector.hasAlpha ? colGreen : colRed, fontSmall,
                "Kenh Alpha trong suot: %s", g_detector.hasAlpha ? "CO (Tach san)" : "KHONG (Nen dac - OPAQUE_WALL)");
            DrawFormatStringToHandle(infoX, infoY + 116, colAmber, fontSmall, "Chroma key de xuat: %s", g_detector.chromaKey.c_str());
            DrawFormatStringToHandle(infoX, infoY + 138, (g_detector.errorCode == "NONE") ? colGreen : colRed, fontSmall,
                "Ma loi: %s", g_detector.errorCode.c_str());

            drawRoundedPanel(infoX, infoY + 166, 506, 90, GetColor(18, 21, 32), colBorder);
            DrawStringToHandle(infoX + 12, infoY + 176, "Giai thich & Khuyen nghi:", colPink, fontBold);
            DrawStringToHandle(infoX + 12, infoY + 200, g_detector.message.c_str(), colWhite, fontSmall);

            // Action Buttons
            DrawStringToHandle(rX + 18, rY + 320, "CAC HANH DONG XU LY ANH CO THE THUC HIEN:", colPink, fontBold);

            // Button 1: 1-Click Cutout if opaque
            unsigned int cutoutCol = (!g_detector.hasAlpha) ? colPink : colCard;
            buttons.push_back({ rX + 18, rY + 348, 788, 44, "⚡ 1-Click Tach Nen Trong Suot (Auto Cutout Nen Dac)", "act_cutout", cutoutCol, colWhite });

            // Button 2: Smart Auto-Detect & Slice
            buttons.push_back({ rX + 18, rY + 400, 788, 44, "✂️ Cat Tu Dong Sprite Sheet (Auto-Slice 2s vao Runs)", "act_slice", colGreen, colWhite });

            // Button 3: Seamless Background
            buttons.push_back({ rX + 18, rY + 452, 788, 44, "🗺️ Tao San Cuon Vo Tan (Make Seamless Horizontal Tile)", "act_seamless", colCyan, colWhite });

            // Button 4: AI Sprite pipeline
            buttons.push_back({ rX + 18, rY + 504, 788, 44, "🤖 Dung Anh Nay Lam Mau De AI Ve Sprite (Codex CLI Pipeline)", "act_ai_regen", colViolet, colWhite });

            // Button 5: Back to Stage
            buttons.push_back({ rX + 18, rY + 576, 788, 42, "▶ Quay Lai San Khau & Kiem Tra Frame Ngay", "goto_stage", colCard, colWhite });
        }

        // TAB 2: STABILIZER & CURATION HUB
        else if (g_activeTab == 2) {
            drawRoundedPanel(12, 60, 1256, 648, colPanel, colBorder);
            DrawStringToHandle(24, 74, "BO DIEU CHINH ON DINH CHUYEN DONG & HIEN THI (AUTO-STABILIZER HUB)", colPink, fontTitle);
            DrawStringToHandle(24, 106, "Tu dong triet tieu rung dau (Head Drift), loai bo khung hinh bi khung (Stalled), va tao lop tho (Idle Breathe).", colMuted, fontSmall);

            // 3 Action Cards
            int cW = 394, cH = 320, cY = 138;

            // Card 1: 1-Click Stabilize
            drawRoundedPanel(24, cY, cW, cH, colCard, colViolet);
            DrawStringToHandle(38, cY + 16, "1. 1-CLICK AUTO-STABILIZE", colViolet, fontBold);
            DrawStringToHandle(38, cY + 44, "- Can chinh toa do (dx, dy) tung frame", colWhite, fontSmall);
            DrawStringToHandle(38, cY + 64, "- Khoa truc dau head_dx khong bi rung lac", colWhite, fontSmall);
            DrawStringToHandle(38, cY + 84, "- Tu dong loai bo frame R_leg < 5% (dung yen)", colWhite, fontSmall);
            DrawStringToHandle(38, cY + 104, "- Bao toan it nhat 3 frame cho moi chu ky", colWhite, fontSmall);
            DrawStringToHandle(38, cY + 124, "- Cap nhat curation.json va ghep lai atlas", colWhite, fontSmall);
            buttons.push_back({ 38, cY + 180, cW - 28, 42, "⚡ Chay 1-Click Stabilize Ngay", "act_stabilize_run", colViolet, colWhite });
            buttons.push_back({ 38, cY + 232, cW - 28, 38, "↺ Khoi Phuc Curation Goc (Reset)", "reset", colCard, colWhite });

            // Card 2: Idle Breathe
            drawRoundedPanel(440, cY, cW, cH, colCard, colPink);
            DrawStringToHandle(454, cY + 16, "2. LOP THO TU NHIEN (IDLE BREATHE)", colPink, fontBold);
            DrawStringToHandle(454, cY + 44, "- Tao nhip tho phong / xep nhe cho nhan vat", colWhite, fontSmall);
            DrawStringToHandle(454, cY + 64, "- Che do Smooth: Bien dang nhe nhe muot ma", colWhite, fontSmall);
            DrawStringToHandle(454, cY + 84, "- Che do Pixel: Giu chat luong pixel art goc", colWhite, fontSmall);
            DrawFormatStringToHandle(454, cY + 114, colCyan, fontSmall, "Che do hien tai: %s", g_breatheMode.c_str());
            buttons.push_back({ 454, cY + 180, cW - 28, 42, "🌬️ Bat Tho Kieu Smooth", "breathe_smooth", (g_breatheMode == "smooth") ? colPink : colCard, colWhite });
            buttons.push_back({ 454, cY + 232, cW - 28, 38, "👾 Bat Tho Kieu Pixel Art", "breathe_pixel", (g_breatheMode == "pixel") ? colPink : colCard, colWhite });

            // Card 3: Advanced Frame In-between & Re-roll
            drawRoundedPanel(856, cY, cW, cH, colCard, colCyan);
            DrawStringToHandle(870, cY + 16, "3. VE LAI HOAC NOI SUY FRAME", colCyan, fontBold);
            DrawStringToHandle(870, cY + 44, "- Re-roll State: Ve lai rieng 1 dong tac chua ung", colWhite, fontSmall);
            DrawStringToHandle(870, cY + 64, "- In-between: Tao frame chuyen tiep trung gian", colWhite, fontSmall);
            DrawStringToHandle(870, cY + 84, "- Giup chuyen dong giua 2 frame muot ma hon", colWhite, fontSmall);
            buttons.push_back({ 870, cY + 180, cW - 28, 42, "🔄 Re-roll State (" + g_currentState + ")", "act_reroll", colCyan, colWhite });
            buttons.push_back({ 870, cY + 232, cW - 28, 38, "✨ AI In-between Frame (0 -> 1)", "act_inbetween", colCard, colWhite });

            // Bottom Full-width summary
            int bBoxY = 480;
            drawRoundedPanel(24, bBoxY, 1226, 210, GetColor(18, 21, 32), colBorder);
            DrawStringToHandle(38, bBoxY + 16, "TRANG THAI HIEN TAI CUA TOAN BO ANIMATION STATES:", colPink, fontBold);
            int sy = bBoxY + 46;
            for (const auto& sname : g_stateOrder) {
                const auto& sd = g_states[sname];
                unsigned int stColor = (sd.status == "NORMAL") ? colGreen : colRed;
                DrawFormatStringToHandle(38, sy, stColor, fontBold,
                    "* State '%s': %s | FPS: %.1f | So frame: %d | Lech dau: %d frames | Khung <5%%: %d | Nhay >35%%: %d",
                    sname.c_str(), sd.status.c_str(), sd.fps, (int)sd.frames.size(), sd.headDriftCount, sd.stalledCount, sd.jumpCutCount);
                sy += 26;
            }
            buttons.push_back({ 38, bBoxY + 150, 240, 38, "▶ Xem Thu Tren San Khau", "goto_stage", colGreen, colWhite });
        }

        // TAB 3: CODE & ASSET EXPORT HUB
        else if (g_activeTab == 3) {
            drawRoundedPanel(12, 60, 1256, 648, colPanel, colBorder);
            DrawStringToHandle(24, 74, "TRINH XUAT MA NGUON & TAI NGUYEN (CODE & ASSET EXPORTER HUB)", colPink, fontTitle);
            DrawStringToHandle(24, 106, "Xuat ma nguon san sang su dung, kem toa do cat frame chinh xac cho tung Game Engine.", colMuted, fontSmall);

            // 5 Engine Export Cards
            struct EngDef { std::string name, ext, desc, id; unsigned int color; };
            std::vector<EngDef> engs = {
                { "C++ & DxLib", ".cpp", "File dxlib_sprite_runner.cpp dung DerivationGraph & DrawExtendGraph", "exp_dxlib", colPink },
                { "HTML5 Canvas", ".html", "Game HTML5 don file nhung san Base64 Sprite Sheet, choi ngay tren trinh duyet", "exp_html5", colGreen },
                { "Phaser 3", ".js", "ES6 Scene script voi anims.create va physics collider", "exp_phaser", colAmber },
                { "Godot 4", ".gd", "CharacterBody2D script voi state machine cho Godot Engine", "exp_godot", colCyan },
                { "Unity C#", ".cs", "SpriteAutoRunner.cs Sprite Sheet Animator cho Unity 2D", "exp_unity", colViolet },
            };

            int startCardY = 140;
            for (size_t i = 0; i < engs.size(); ++i) {
                int eY = startCardY + (int)i * 74;
                drawRoundedPanel(24, eY, 940, 64, colCard, engs[i].color);
                DrawFormatStringToHandle(40, eY + 12, engs[i].color, fontBold, "%s (%s)", engs[i].name.c_str(), engs[i].ext.c_str());
                DrawStringToHandle(40, eY + 36, engs[i].desc.c_str(), colMuted, fontSmall);
                buttons.push_back({ 780, eY + 14, 170, 36, "Xuat file " + engs[i].ext, engs[i].id, engs[i].color, colWhite });
            }

            // Right Action Column (290px)
            int rX = 980, rY = 140, rW = 288, rH = 550;
            drawRoundedPanel(rX, rY, rW, rH, colPanel, colBorder);
            DrawStringToHandle(rX + 16, rY + 16, "THAO TAC XUAT BUNDLE", colPink, fontBold);

            buttons.push_back({ rX + 16, rY + 46, rW - 32, 44, "🚀 XUAT TAT CA ENGINE (1-Click)", "exp_all", colGreen, colWhite });
            buttons.push_back({ rX + 16, rY + 100, rW - 32, 44, "📦 Xuat Asset Bundle (PNG+GIF+JSON)", "exp_bundle", colViolet, colWhite });
            buttons.push_back({ rX + 16, rY + 164, rW - 32, 40, "📂 Mo Thu Muc exported_code/", "open_export_dir", colCard, colWhite });
            buttons.push_back({ rX + 16, rY + 214, rW - 32, 40, "🌐 Mo Web Studio (127.0.0.1:8780)", "open_web", colCard, colWhite });
            buttons.push_back({ rX + 16, rY + 264, rW - 32, 40, "💻 Mo Project trong Antigravity IDE", "open_ide", colCard, colWhite });

            DrawStringToHandle(rX + 16, rY + 330, "File da xuat duoc luu tai:", colWhite, fontSmall);
            DrawStringToHandle(rX + 16, rY + 352, "projects/jirai-neko-demo/", colCyan, fontSmall);
            DrawStringToHandle(rX + 16, rY + 372, "  exported_code/", colCyan, fontSmall);
            DrawStringToHandle(rX + 16, rY + 392, "  - dxlib_sprite_runner.cpp", colMuted, fontSmall);
            DrawStringToHandle(rX + 16, rY + 410, "  - html5_autorun_game.html", colMuted, fontSmall);
            DrawStringToHandle(rX + 16, rY + 428, "  - phaser3_autorun_scene.js", colMuted, fontSmall);
            DrawStringToHandle(rX + 16, rY + 446, "  - godot4_character.gd", colMuted, fontSmall);
            DrawStringToHandle(rX + 16, rY + 464, "  - SpriteAutoRunner.cs", colMuted, fontSmall);
        }

        // 5. RENDER ALL BUTTONS & PROCESS CLICKS
        for (const auto& b : buttons) {
            bool hov = b.contains(mx, my);
            unsigned int fill = b.bgCol;
            if (b.active) fill = colPink;
            else if (hov) fill = GetColor(std::min(255, (int)(fill & 0xFF) + 30), std::min(255, (int)((fill >> 8) & 0xFF) + 30), std::min(255, (int)((fill >> 16) & 0xFF) + 30));

            DrawBox(b.x, b.y, b.x + b.w, b.y + b.h, fill, TRUE);
            DrawBox(b.x, b.y, b.x + b.w, b.y + b.h, (hov || b.active) ? colWhite : colBorder, FALSE);
            DrawStringToHandle(b.x + 8, b.y + (b.h - 14) / 2, b.label.c_str(), b.textCol, fontSmall);

            if (clicked && hov) {
                // Tab switching
                if (b.id.rfind("tab_", 0) == 0) {
                    g_activeTab = std::stoi(b.id.substr(4));
                } else if (b.id == "goto_stage") {
                    g_activeTab = 0;
                }
                // File Browse Dialog
                else if (b.id == "dlg_import" || b.id == "quick_browse") {
                    std::string chosen = openImageFileDialog();
                    if (!chosen.empty()) {
                        runPythonBridgeAsync("import_file --file \"" + chosen + "\"",
                            "Dang nhap anh: " + chosen + "...",
                            "Anh da duoc nhap va kiem dinh thanh cong!");
                    }
                }
                // Input switching
                else if (b.id.rfind("sel_inp_", 0) == 0) {
                    std::string inName = b.id.substr(8);
                    runPythonBridgeAsync("select_input --input \"" + inName + "\"",
                        "Dang chuyen sang anh: " + inName + "...",
                        "Da chon anh: " + inName);
                }
                // Cutout
                else if (b.id == "act_cutout") {
                    runPythonBridgeAsync("cutout", "Dang tach nen trong suot (1-Click Cutout)...", "Tach nen thanh cong! File moi da san sang.");
                }
                // Slice Sheet
                else if (b.id == "act_slice") {
                    runPythonBridgeAsync("slice_sheet", "Dang cat Sprite Sheet (Auto-Slice 2s)...", "Cat khung hinh thanh cong!");
                }
                // Seamless BG
                else if (b.id == "act_seamless") {
                    runPythonBridgeAsync("seamless_bg", "Dang tao san cuon vo tan (Seamless Tile)...", "Da tao xong seamless_stage_bg.png!");
                }
                // AI pipeline
                else if (b.id == "act_ai_regen") {
                    runPythonBridgeAsync("ai_regen", "Dang goi Codex CLI tao sprite tu anh mau...", "AI tao bo sprite hoan tat!");
                }
                // Stabilize
                else if (b.id == "stabilize" || b.id == "act_stabilize_run") {
                    runPythonBridgeAsync("stabilize --run " + g_activeRun + " --breathe-mode " + g_breatheMode,
                        "Dang chay 1-Click Auto-Stabilize...",
                        "Da triet tieu rung dau va loc khung khung!");
                }
                // Reset
                else if (b.id == "reset") {
                    runPythonBridgeAsync("reset --run " + g_activeRun, "Dang khoi phuc frame goc...", "Da khoi phuc curation.json goc!");
                }
                // Breathe toggle
                else if (b.id == "breathe_smooth") {
                    g_breatheMode = "smooth";
                    runPythonBridgeAsync("stabilize --run " + g_activeRun + " --breathe-mode smooth", "Dang bat che do tho Smooth...", "Da ap dung che do tho Smooth!");
                } else if (b.id == "breathe_pixel") {
                    g_breatheMode = "pixel";
                    runPythonBridgeAsync("stabilize --run " + g_activeRun + " --breathe-mode pixel", "Dang bat che do tho Pixel Art...", "Da ap dung che do tho Pixel Art!");
                }
                // Re-roll
                else if (b.id == "act_reroll") {
                    runPythonBridgeAsync("reroll_state --run " + g_activeRun + " --state " + g_currentState,
                        "Dang ve lai state " + g_currentState + "...", "Da ve lai state " + g_currentState + "!");
                }
                // In-between
                else if (b.id == "act_inbetween") {
                    runPythonBridgeAsync("inbetween --run " + g_activeRun + " --state " + g_currentState + " --frame 0",
                        "Dang tao frame noi suy in-between...", "Da tao frame in-between!");
                }
                // Switch Run
                else if (b.id == "switch_run" && g_availableRuns.size() >= 2) {
                    std::string nextRun = (g_activeRun == "codex_run") ? "unpacked_run" : "codex_run";
                    runPythonBridgeAsync("sync --run " + nextRun, "Dang doi sang " + nextRun + "...", "Da doi sang " + nextRun);
                }
                // FPS adjustments
                else if (b.id == "fps_dec") {
                    float newFps = std::max(1.0f, g_states[g_currentState].fps - 1.0f);
                    runPythonBridgeAsync("set_fps --run " + g_activeRun + " --state " + g_currentState + " --fps " + std::to_string(newFps), "Dang giam FPS...", "Da cap nhat FPS");
                } else if (b.id == "fps_inc") {
                    float newFps = std::min(60.0f, g_states[g_currentState].fps + 1.0f);
                    runPythonBridgeAsync("set_fps --run " + g_activeRun + " --state " + g_currentState + " --fps " + std::to_string(newFps), "Dang tang FPS...", "Da cap nhat FPS");
                }
                // Stage toggles
                else if (b.id == "toggle_forward") forwardLoop = !forwardLoop;
                else if (b.id == "toggle_pixel")   pixelMode = !pixelMode;
                else if (b.id == "toggle_zoom")    zoom = (zoom % 3) + 1;
                else if (b.id == "toggle_guides")  showGuides = !showGuides;
                else if (b.id.rfind("state_", 0) == 0) {
                    g_currentState = b.id.substr(6);
                    animCursor = 0;
                }
                // Frame nudge
                else if (b.id.rfind("f_", 0) == 0) {
                    size_t secondUnderscore = b.id.find('_', 2);
                    int fIdx = std::stoi(b.id.substr(2, secondUnderscore - 2));
                    std::string op = b.id.substr(secondUnderscore + 1);
                    std::ostringstream oss;
                    oss << "nudge --run " << g_activeRun << " --state " << g_currentState << " --frame " << fIdx;
                    if (op == "dx_neg") oss << " --dx -1";
                    else if (op == "dx_pos") oss << " --dx 1";
                    else if (op == "tog") oss << " --toggle";
                    runPythonBridgeAsync(oss.str(), "Dang cap nhat frame #" + std::to_string(fIdx) + "...", "Da cap nhat frame!");
                }
                // Exports
                else if (b.id == "export_code" || b.id == "exp_all") {
                    runPythonBridgeAsync("export --run " + g_activeRun + " --engine all", "Dang xuat tat ca engine code...", "Da xuat xong C++, HTML5, Phaser, Godot, Unity vao exported_code/!");
                    ShellExecuteA(NULL, "open", "projects\\jirai-neko-demo\\exported_code", NULL, NULL, SW_SHOWNORMAL);
                } else if (b.id == "exp_bundle") {
                    runPythonBridgeAsync("export --run " + g_activeRun + " --engine bundle", "Dang xuat Asset Bundle...", "Da xuat Asset Bundle vao exported_code/asset_bundle/!");
                    ShellExecuteA(NULL, "open", "projects\\jirai-neko-demo\\exported_code\\asset_bundle", NULL, NULL, SW_SHOWNORMAL);
                } else if (b.id.rfind("exp_", 0) == 0) {
                    std::string engName = b.id.substr(4);
                    runPythonBridgeAsync("export --run " + g_activeRun + " --engine " + engName, "Dang xuat file " + engName + "...", "Da xuat file " + engName + "!");
                } else if (b.id == "open_export_dir") {
                    ShellExecuteA(NULL, "open", "projects\\jirai-neko-demo\\exported_code", NULL, NULL, SW_SHOWNORMAL);
                } else if (b.id == "open_web") {
                    ShellExecuteA(NULL, "open", "http://127.0.0.1:8780", NULL, NULL, SW_SHOWNORMAL);
                } else if (b.id == "open_ide") {
                    ShellExecuteA(NULL, "open", ".", NULL, NULL, SW_SHOWNORMAL);
                }
            }
        }

        ScreenFlip();
    }

    if (g_atlasHandle != -1) DeleteGraph(g_atlasHandle);
    if (g_inputThumbHandle != -1) DeleteGraph(g_inputThumbHandle);
    DeleteFontToHandle(fontTitle);
    DeleteFontToHandle(fontTab);
    DeleteFontToHandle(fontBold);
    DeleteFontToHandle(fontSmall);
    DxLib_End();
    return 0;
}
