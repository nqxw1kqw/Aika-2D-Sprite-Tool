@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Enterprise\VC\Auxiliary\Build\vcvars64.bat"
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%

cd /d "%~dp0.."
cl.exe /nologo /EHsc /std:c++17 /MT /O2 /utf-8 /wd4819 /wd4828 ^
  /I"C:\DxLib_Normal" ^
  "dxlib_app\main.cpp" ^
  /Fe:"AikaSpriteStudioDxLib.exe" ^
  /Fo:"dxlib_app\main.obj" ^
  /link /LIBPATH:"C:\DxLib_Normal" user32.lib gdi32.lib shell32.lib ole32.lib comdlg32.lib /SUBSYSTEM:WINDOWS
