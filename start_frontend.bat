@echo off
chcp 65001 >nul 2>&1
title 桥梁数字孪生平台 - 前端
cd /d D:\bridge-digital-twin-platform\frontend

echo ============================================
echo   桥梁数字孪生平台 - 前端服务
echo ============================================
echo.

:: 清理占用 5173 端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173.*LISTENING"') do (
    echo [INFO] 清理端口 5173 残留进程 PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo [INFO] 正在启动 Vite 开发服务器...
echo [INFO] 启动成功后浏览器打开 http://localhost:5173
echo.
echo ============================================
echo.

call D:\pnpm\global\pnpm.cmd dev

echo.
echo ============================================
echo   前端已停止
echo ============================================
pause
