@echo off
chcp 65001 >nul
title Aika 2D Sprite Auto-Run Studio v2.0
cd /d "%~dp0"

echo ========================================================
echo   🎀 Aika 2D Sprite Auto-Run Studio v2.0
echo   Binding strictly to http://127.0.0.1:8780
echo ========================================================

start "" "http://127.0.0.1:8780"
".venv\bin\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8780
