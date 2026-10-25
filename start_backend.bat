@echo off
title 桥梁数字孪生平台 - 后端
cd /d "%~dp0backend"

echo ============================================
echo   桥梁数字孪生平台 - 后端服务
echo ============================================
echo.

:: 先杀掉可能占用 8000 的残留进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000.*LISTENING"') do (
    echo 清理端口 8000 残留进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON=py"
)

echo 正在启动 FastAPI 后端...
echo.
"%PYTHON%" -m uvicorn app.main:app --port 8000

echo.
echo ============================================
echo   后端已停止，按任意键关闭窗口
echo ============================================
pause