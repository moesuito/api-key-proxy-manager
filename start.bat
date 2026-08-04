@echo off
title NVIDIA NIM API Proxy
echo ===================================================
echo   Iniciando NVIDIA NIM API Proxy...
echo ===================================================

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERRO] Ambiente virtual .venv nao encontrado!
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m app.main

pause
