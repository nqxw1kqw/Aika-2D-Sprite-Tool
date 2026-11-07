// C++ & DxLib 2D Sprite Auto-Runner for `jirai_neko`
// Compile with Visual Studio + C:\DxLib_Normal (64-bit /MT)
#include "DxLib.h"
#include <map>
#include <string>
#include <vector>

struct FrameRect { int x, y, w, h; };
struct AnimState {
    float fps;
    std::vector<FrameRect> frames;
};

int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {
    ChangeWindowMode(TRUE);
    SetGraphMode(960, 540, 32);
    SetMainWindowText("DxLib 2D Sprite Auto-Run - jirai_neko");
    if (DxLib_Init() == -1) return -1;
    SetDrawScreen(DX_SCREEN_BACK);

    int atlasHandle = LoadGraph("sprite-sheet-alpha.png");
    std::map<std::string, AnimState> states = {
        { "idle", { 5.0f, { {0, 0, 256, 256}, {256, 0, 256, 256}, {512, 0, 256, 256}, {768, 0, 256, 256} } } },
        { "walk", { 8.0f, { {0, 256, 256, 256}, {256, 256, 256, 256}, {512, 256, 256, 256}, {768, 256, 256, 256}, {1024, 256, 256, 256}, {1280, 256, 256, 256} } } },
    };

    std::string currentState = "walk";
    bool pixelArtMode = false;
    bool forwardLoop = true;
    int zoom = 1;
    float actorX = 480.0f, actorY = 0.0f, vy = 0.0f, scrollX = 0.0f;
    bool flipX = false;
    int frameIdx = 0;
    int lastTick = GetNowCount();

    while (ProcessMessage() == 0 && CheckHitKey(KEY_INPUT_ESCAPE) == 0) {
        ClearDrawScreen();

        // Keyboard controls: A/D or Left/Right to move, Space to jump, P to toggle Pixel Art
        if (CheckHitKey(KEY_INPUT_RIGHT) || CheckHitKey(KEY_INPUT_D)) {
            flipX = false; scrollX += 4.0f;
            if (states.count("walk")) currentState = "walk";
        } else if (CheckHitKey(KEY_INPUT_LEFT) || CheckHitKey(KEY_INPUT_A)) {
            flipX = true; scrollX -= 4.0f;
            if (states.count("walk")) currentState = "walk";
        } else if (forwardLoop) {
            scrollX += 3.0f;
        }

        if (CheckHitKey(KEY_INPUT_SPACE) && actorY == 0.0f) vy = -11.0f;
        if (actorY < 0.0f || vy < 0.0f) {
            actorY += vy; vy += 0.55f;
            if (actorY >= 0.0f) { actorY = 0.0f; vy = 0.0f; }
        }

        const AnimState& st = states[currentState];
        int now = GetNowCount();
        int intervalMs = (int)(1000.0f / (st.fps > 0.0f ? st.fps : 8.0f));
        if (!st.frames.empty() && now - lastTick >= intervalMs) {
            frameIdx = (frameIdx + 1) % (int)st.frames.size();
            lastTick = now;
        }

        // Draw procedural ground & scrolling 64px ruler ticks
        int groundY = 460;
        DrawLine(0, groundY, 960, groundY, GetColor(110, 100, 145), 2);
        int offset = ((int)scrollX % 64 + 64) % 64;
        for (int tx = -offset; tx < 960; tx += 64) {
            DrawLine(tx, groundY, tx, groundY + 10, GetColor(85, 80, 115), 2);
        }

        if (atlasHandle != -1 && !st.frames.empty()) {
            const FrameRect& fr = st.frames[frameIdx % st.frames.size()];
            int subH = DerivationGraph(fr.x, fr.y, fr.w, fr.h, atlasHandle);
            int drawW = fr.w * zoom;
            int drawH = fr.h * zoom;
            int topY = groundY - drawH + (int)actorY;

            // Projected dynamic shadow
            SetDrawBlendMode(DX_BLENDMODE_ALPHA, 120);
            DrawOval((int)actorX, groundY - 2, (int)(drawW * 0.22f), 7, GetColor(10, 10, 18), TRUE);
            SetDrawBlendMode(DX_BLENDMODE_NOBLEND, 0);

            SetDrawMode(pixelArtMode ? DX_DRAWMODE_NEAREST : DX_DRAWMODE_BILINEAR);
            if (!flipX) {
                DrawExtendGraph((int)actorX - drawW / 2, topY, (int)actorX + drawW / 2, topY + drawH, subH, TRUE);
            } else {
                DrawExtendGraph((int)actorX + drawW / 2, topY, (int)actorX - drawW / 2, topY + drawH, subH, TRUE);
            }
            DeleteGraph(subH);
        }

        DrawFormatString(20, 20, GetColor(244, 114, 182),
            "DxLib Sprite Auto-Run [%s] | State: %s | Frame: %d/%d | A/D: Move, Space: Jump, ESC: Quit",
            "jirai_neko", currentState.c_str(), frameIdx + 1, (int)st.frames.size());

        ScreenFlip();
    }

    DxLib_End();
    return 0;
}
