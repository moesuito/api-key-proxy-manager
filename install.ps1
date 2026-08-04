# =====================================================================
# NVIDIA NIM API Proxy Manager - One-Liner PowerShell Installer
# Installs nimproxy into %APPDATA%\nimproxy and sets up PATH
# =====================================================================

param(
    [switch]$NoSetup
)

$ErrorActionPreference = "Stop"

$AppName = "nimproxy"
$InstallDir = Join-Path $env:APPDATA $AppName
$BinDir = Join-Path $InstallDir "bin"
$RepoUrl = "https://github.com/moesuito/api-key-proxy-manager"
$ZipUrl = "$RepoUrl/archive/refs/heads/v0.2.0.zip"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   Installing NVIDIA NIM API Proxy Manager (nimproxy)..." -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python installation
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    Write-Host "[ERROR] Python 3 was not found in your system PATH." -ForegroundColor Red
    Write-Host "Please install Python 3 (https://www.python.org/downloads/) and rerun this installer." -ForegroundColor Yellow
    exit 1
}

# 2. Create Target Directories
Write-Host "[1/5] Creating application directory at $InstallDir..." -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

# 3. Copy/Download Source Files
Write-Host "[2/5] Deploying nimproxy source files..." -ForegroundColor Green
$CurrentScriptDir = $PSScriptRoot
if ($CurrentScriptDir -and (Test-Path (Join-Path $CurrentScriptDir "cli.py"))) {
    # Installed from local directory
    Copy-Item -Path (Join-Path $CurrentScriptDir "app") -Destination $InstallDir -Recurse -Force
    Copy-Item -Path (Join-Path $CurrentScriptDir "tests") -Destination $InstallDir -Recurse -Force
    Copy-Item -Path (Join-Path $CurrentScriptDir "cli.py") -Destination $InstallDir -Force
    Copy-Item -Path (Join-Path $CurrentScriptDir "requirements.txt") -Destination $InstallDir -Force
    Copy-Item -Path (Join-Path $CurrentScriptDir "README.md") -Destination $InstallDir -Force
    Copy-Item -Path (Join-Path $CurrentScriptDir ".env.example") -Destination $InstallDir -Force
} else {
    # Installed via web (irm | iex)
    $ZipPath = Join-Path $env:TEMP "nimproxy-source.zip"
    Write-Host "      Downloading latest source package from GitHub..." -ForegroundColor Gray
    Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath
    
    $ExtractTemp = Join-Path $env:TEMP "nimproxy-extract"
    if (Test-Path $ExtractTemp) { Remove-Item -Path $ExtractTemp -Recurse -Force }
    Expand-Archive -Path $ZipPath -DestinationPath $ExtractTemp -Force
    
    $SubFolder = Get-ChildItem -Path $ExtractTemp | Select-Object -First 1
    Copy-Item -Path (Join-Path $SubFolder.FullName "*") -Destination $InstallDir -Recurse -Force
}

# 4. Setup Python Virtual Environment
Write-Host "[3/5] Setting up Python virtual environment (.venv)..." -ForegroundColor Green
$VenvDir = Join-Path $InstallDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    & python -m venv $VenvDir
}

Write-Host "      Installing Python dependencies (fastapi, uvicorn, httpx, python-dotenv)..." -ForegroundColor Gray
& $VenvPip install -r (Join-Path $InstallDir "requirements.txt") --quiet --no-warn-script-location

# 5. Create nimproxy CMD CLI Wrapper
Write-Host "[4/5] Creating executable CLI wrapper (nimproxy)..." -ForegroundColor Green
$CmdWrapperPath = Join-Path $BinDir "nimproxy.cmd"
$CmdContent = @"
@echo off
"$VenvPython" "$InstallDir\cli.py" %*
"@
Set-Content -Path $CmdWrapperPath -Value $CmdContent -Encoding ASCII

# 6. Add BinDir to User PATH Environment Variable
Write-Host "[5/5] Configuring User PATH environment variable..." -ForegroundColor Green
$UserPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($UserPath -notlike "*$BinDir*") {
    $NewUserPath = "$BinDir;$UserPath"
    [Environment]::SetEnvironmentVariable("PATH", $NewUserPath, "User")
    $env:PATH = "$BinDir;$env:PATH"
    Write-Host "      Added $BinDir to User PATH." -ForegroundColor Gray
} else {
    Write-Host "      $BinDir is already in User PATH." -ForegroundColor Gray
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   INSTALLATION COMPLETE!" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host ""

if (-not $NoSetup) {
    & $VenvPython (Join-Path $InstallDir "cli.py") --setup
}
