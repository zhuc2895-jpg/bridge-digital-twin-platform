@echo off
chcp 65001 >nul 2>&1
title 桥梁数字孪生平台 - 前端
cd /d "%~dp0frontend"

echo ============================================
echo   桥梁数字孪生平台 - 前端服务
echo ============================================
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173.*LISTENING"') do (
    echo [INFO] 清理端口 5173 残留进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

where pnpm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 pnpm，请先安装 Node.js 并启用 Corepack。
    pause
    exit /b 1
)

echo [INFO] 正在启动 Vite 开发服务器...
echo [INFO] 启动成功后浏览器打开 http://localhost:5173
echo.
echo ============================================
echo.

call pnpm dev

echo.
echo ============================================
echo   前端已停止
pause
