@echo off
chcp 65001 >nul 2>&1
setlocal
set "ROOT=%~dp0"

if exist "%ROOT%dist-windows\BridgeDigitalTwin\BridgeDigitalTwin.exe" (
    start "" "%ROOT%dist-windows\BridgeDigitalTwin\BridgeDigitalTwin.exe"
    exit /b 0
)

echo Windows package not found. Starting the desktop shell from source...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\run_desktop.ps1"

