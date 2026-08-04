@echo off
title NVIDIA NIM API Proxy
echo ===================================================
echo   Starting NVIDIA NIM API Proxy...
echo ===================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment .venv not found!
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m app.main

pause
