import os
import sys
import json
import time
import zipfile
import winreg
import urllib.request
import subprocess
from typing import List, Dict, Tuple, Optional

import httpx

from app.config import settings, get_app_dir, save_config_data, load_config_data, APP_VERSION


def get_server_pid_file() -> str:
    return os.path.join(get_app_dir(), "server.pid")


def save_server_pid(pid: int):
    with open(get_server_pid_file(), "w", encoding="utf-8") as f:
        f.write(str(pid))


def load_server_pid() -> Optional[int]:
    pid_file = get_server_pid_file()
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                return int(f.read().strip())
        except Exception:
            pass
    return None


def is_server_running() -> Tuple[bool, Optional[Dict]]:
    """Checks if nimproxy server is running locally on http://localhost:8000/health."""
    url = f"http://localhost:{settings.PORT}/health"
    try:
        resp = httpx.get(url, timeout=1.5)
        if resp.status_code == 200:
            return True, resp.json()
    except Exception:
        pass
    return False, None


def find_pythonw_executable() -> str:
    """Finds pythonw.exe or python.exe to run completely detached in background."""
    app_dir = get_app_dir()
    venv_pythonw = os.path.join(app_dir, ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(venv_pythonw):
        return venv_pythonw
    
    local_venv_pythonw = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "Scripts", "pythonw.exe")
    if os.path.exists(local_venv_pythonw):
        return local_venv_pythonw

    # Fallback to python.exe
    return sys.executable


def start_background_server() -> bool:
    """Launches the server in background as a detached process."""
    running, _ = is_server_running()
    if running:
        return True

    python_bin = find_pythonw_executable()
    app_dir = get_app_dir()
    
    # Detached creation flag for Windows
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)

    proc = subprocess.Popen(
        [python_bin, "-m", "app.main"],
        cwd=app_dir,
        creationflags=creationflags
    )
    
    save_server_pid(proc.pid)

    # Wait up to 5 seconds for startup
    for _ in range(10):
        time.sleep(0.5)
        running, health = is_server_running()
        if running:
            return True

    return False


def stop_background_server() -> bool:
    """Stops the background server process."""
    pid = load_server_pid()
    if pid and sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    # Also kill any python process listening on port 8000 if pid failed
    time.sleep(0.5)
    running, _ = is_server_running()
    return not running


def set_windows_autostart(enable: bool):
    """Adds or removes nimproxy from Windows Registry Startup."""
    if sys.platform != "win32":
        return

    reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    python_bin = find_pythonw_executable()
    app_dir = get_app_dir()
    cmd = f'"{python_bin}" -m app.main'

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, "nimproxy", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "nimproxy")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Warning] Failed to update Windows Registry startup: {e}")


def fetch_available_models(keys: List[str]) -> List[str]:
    """Fetches list of available models from NVIDIA NIM using configured keys."""
    url = f"{settings.NVIDIA_BASE_URL}/models"
    for k in keys:
        try:
            resp = httpx.get(url, headers={"Authorization": f"Bearer {k}"}, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                models = [m["id"] for m in data.get("data", []) if "id" in m]
                if models:
                    return sorted(models)
        except Exception:
            pass
    return []


def run_interactive_setup():
    """Guided terminal setup flow."""
    print("=" * 65)
    print("   NVIDIA NIM API Proxy Manager - Guided Setup (v0.2.0)")
    print("=" * 65)
    print()

    # Step 1: Autostart Selection
    autostart_str = input("Start nimproxy automatically when Windows boots? [Y/n]: ").strip().lower()
    autostart = autostart_str != 'n'

    # Step 2: API Keys Loop
    print("\n--- Step 1: NVIDIA NIM API Keys Configuration ---")
    print("You can register multiple API keys for automatic failover.")
    print("Enter at least 1 API Key.\n")

    keys: List[str] = []
    key_counter = 1
    while True:
        prompt = f"Enter NVIDIA NIM API Key #{key_counter}"
        if key_counter > 1:
            prompt += " (Press Enter to finish)"
        prompt += ": "
        
        user_key = input(prompt).strip()
        if not user_key:
            if len(keys) >= 1:
                break
            else:
                print("[!] At least 1 API Key is required. Please enter a valid API key.")
                continue
        
        if user_key in keys:
            print("[!] Key already added. Enter a different key.")
            continue

        keys.append(user_key)
        print(f"    [+] Key #{key_counter} added successfully! ({user_key[:4]}...{user_key[-4:]})")
        key_counter += 1

    # Step 3: Model Fetching & Selection
    print("\n--- Step 2: Model Selection ---")
    print("Fetching available models from NVIDIA NIM...")
    fetched_models = fetch_available_models(keys)

    recommended_model = "z-ai/glm-5.2"
    selected_model = recommended_model

    if fetched_models:
        print("\nAvailable Models on NVIDIA NIM:")
        
        # Ensure recommended model is listed first
        display_models = []
        if recommended_model in fetched_models:
            display_models.append(recommended_model)
            for m in fetched_models:
                if m != recommended_model:
                    display_models.append(m)
        else:
            display_models = [recommended_model] + fetched_models

        # Display top 10 models
        for idx, m in enumerate(display_models[:15], 1):
            rec_tag = " (Recommended)" if m == recommended_model else ""
            print(f"  {idx}. {m}{rec_tag}")
        
        print(f"  0. Enter custom model name manually")
        
        choice = input(f"\nSelect a model number [Default: 1 ({recommended_model})]: ").strip()
        if not choice or choice == "1":
            selected_model = display_models[0]
        elif choice == "0":
            custom_m = input("Enter custom model ID: ").strip()
            if custom_m:
                selected_model = custom_m
        elif choice.isdigit() and 1 <= int(choice) <= len(display_models[:15]):
            selected_model = display_models[int(choice) - 1]
        else:
            # Check if typed model string directly
            if choice in fetched_models:
                selected_model = choice
            else:
                selected_model = recommended_model
    else:
        print(f"[!] Could not fetch model list from NVIDIA NIM. Using default recommended: {recommended_model}")

    print(f"\n[✓] Selected Model: {selected_model}")

    # Step 4: Master Proxy Key
    existing_config = load_config_data()
    proxy_key = existing_config.get("proxy_api_key")
    if not proxy_key:
        import secrets
        proxy_key = f"sk-nim-{secrets.token_hex(16)}"

    # Step 5: Save Config
    config_data = {
        "proxy_api_key": proxy_key,
        "nvidia_api_keys": keys,
        "default_model": selected_model,
        "nvidia_base_url": settings.NVIDIA_BASE_URL,
        "probe_interval_seconds": 30,
        "autostart_windows": autostart,
        "host": "0.0.0.0",
        "port": 8000,
        "version": APP_VERSION
    }
    save_config_data(config_data)
    set_windows_autostart(autostart)

    # Step 6: Start Server in Background
    print("\nStarting background server...")
    success = start_background_server()

    print("\n" + "=" * 65)
    if success:
        print("   SETUP COMPLETE - nimproxy is now running in background!")
    else:
        print("   SETUP COMPLETE - nimproxy configured successfully.")
    print("=" * 65)
    print(f" Master Proxy API Key : {proxy_key}")
    print(f" Active Model        : {selected_model}")
    print(f" OpenAI Endpoint     : http://localhost:8000/v1")
    print(f" Anthropic Endpoint  : http://localhost:8000")
    print(f" Configured Keys     : {len(keys)} Key(s) Active")
    print(f" Windows Autostart   : {'Enabled' if autostart else 'Disabled'}")
    print("=" * 65 + "\n")


def show_status_report(health_data: Dict):
    """Displays a clean non-TUI status summary in terminal."""
    key_mgr = health_data.get("key_manager", {})
    total_keys = key_mgr.get("total_keys", 0)
    active_keys = key_mgr.get("active_keys", 0)
    model = health_data.get("default_model", settings.DEFAULT_MODEL)
    proxy_key = settings.PROXY_API_KEY

    print("=" * 65)
    print("   nimproxy Status: ONLINE (Running in background)")
    print("=" * 65)
    print(f" Version             : v{APP_VERSION}")
    print(f" Active Model        : {model}")
    print(f" Master Proxy Key    : {proxy_key}")
    print(f" OpenAI Endpoint     : http://localhost:{settings.PORT}/v1")
    print(f" Anthropic Endpoint  : http://localhost:{settings.PORT}")
    print(f" Active Key Pool     : {active_keys}/{total_keys} Keys Online")
    print("-----------------------------------------------------------------")
    print(" API Key Details:")
    for k in key_mgr.get("keys", []):
        k_masked = k.get("key")
        k_status = k.get("status", "active").upper()
        reqs = k.get("total_requests", 0)
        errs = k.get("429_errors", 0)
        print(f"   - Key {k_masked}: {k_status} (Total Requests: {reqs}, Rate Limits: {errs})")
    print("=" * 65)
    print(" Commands: 'nimproxy --setup' to reconfigure | 'nimproxy stop' to halt")


def check_for_updates() -> bool:
    """Checks GitHub releases for new version updates."""
    repo_url = "https://api.github.com/repos/moesuito/api-key-proxy-manager/releases/latest"
    try:
        resp = httpx.get(repo_url, timeout=3.0, headers={"User-Agent": "nimproxy-cli"})
        if resp.status_code == 200:
            data = resp.json()
            latest_tag = data.get("tag_name", "").lstrip("v")
            if latest_tag and latest_tag != APP_VERSION:
                print(f"\n[!] New update available: v{latest_tag} (Current: v{APP_VERSION})")
                print(f"    Release info: {data.get('html_url')}\n")
                return True
    except Exception:
        pass
    return False


def main():
    args = sys.argv[1:]

    # Parse CLI commands
    if "--help" in args or "-h" in args:
        print("""
NVIDIA NIM API Proxy Manager CLI (nimproxy)

Usage:
  nimproxy              Display server status or start background server
  nimproxy start        Start background server
  nimproxy stop         Stop background server
  nimproxy restart      Restart background server
  nimproxy setup        Run guided setup wizard
  nimproxy update       Check for new releases on GitHub
  nimproxy version      Display current version
""")
        return

    if "--setup" in args or "setup" in args or "config" in args:
        run_interactive_setup()
        return

    if "stop" in args:
        print("Stopping nimproxy background server...")
        if stop_background_server():
            print("[✓] Server stopped successfully.")
        else:
            print("[!] Server was not running.")
        return

    if "restart" in args:
        print("Restarting nimproxy background server...")
        stop_background_server()
        time.sleep(1)
        if start_background_server():
            print("[✓] Server restarted successfully.")
        else:
            print("[ERRO] Failed to restart server.")
        return

    if "update" in args:
        print(f"Checking for updates (Current version: v{APP_VERSION})...")
        if not check_for_updates():
            print("[✓] nimproxy is already on the latest version!")
        return

    if "version" in args or "--version" in args:
        print(f"nimproxy v{APP_VERSION}")
        return

    # Default action (typing 'nimproxy')
    cfg = load_config_data()
    if not cfg.get("nvidia_api_keys"):
        run_interactive_setup()
        return

    running, health = is_server_running()
    if running and health:
        show_status_report(health)
    else:
        print("nimproxy server is not running. Starting background process...")
        if start_background_server():
            time.sleep(1)
            _, health_after = is_server_running()
            if health_after:
                show_status_report(health_after)
            else:
                print(f"[✓] nimproxy server started successfully in background! (Model: {settings.DEFAULT_MODEL})")
        else:
            print("[ERRO] Failed to start nimproxy server in background.")


if __name__ == "__main__":
    main()
