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

if sys.platform == "win32":
    import msvcrt


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
    """Checks if nimproxy server is running locally on http://localhost:<PORT>/health."""
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

    return sys.executable


def start_background_server() -> bool:
    """Launches the server in background as a detached process."""
    running, _ = is_server_running()
    if running:
        return True

    python_bin = find_pythonw_executable()
    app_dir = get_app_dir()
    
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)

    proc = subprocess.Popen(
        [python_bin, "-m", "app.main"],
        cwd=app_dir,
        creationflags=creationflags
    )
    
    save_server_pid(proc.pid)

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

    time.sleep(0.5)
    running, _ = is_server_running()
    return not running


def restart_background_server() -> bool:
    stop_background_server()
    time.sleep(0.5)
    return start_background_server()


def set_windows_autostart(enable: bool):
    """Adds or removes nimproxy from Windows Registry Startup."""
    if sys.platform != "win32":
        return

    reg_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    python_bin = find_pythonw_executable()
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


def configure_claude_code(proxy_key: str = None, model_name: str = None, port: int = None) -> bool:
    """Configures Claude Code (~/.claude/settings.json) to use nimproxy."""
    user_home = os.path.expanduser("~")
    claude_dir = os.path.join(user_home, ".claude")
    settings_file = os.path.join(claude_dir, "settings.json")

    proxy_key = proxy_key or settings.PROXY_API_KEY
    model_name = model_name or settings.DEFAULT_MODEL
    port = port or settings.PORT

    try:
        os.makedirs(claude_dir, exist_ok=True)
        data = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if "env" not in data or not isinstance(data["env"], dict):
            data["env"] = {}

        data["env"]["ANTHROPIC_BASE_URL"] = f"http://localhost:{port}"
        data["env"]["ANTHROPIC_AUTH_TOKEN"] = proxy_key
        data["env"]["ANTHROPIC_MODEL"] = model_name
        data["env"].pop("ANTHROPIC_API_KEY", None)

        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[OK] Claude Code successfully configured at {settings_file}!")
        print(f"     Base URL   : http://localhost:{port}")
        print(f"     Auth Token : {proxy_key[:8]}...")
        print(f"     Model      : {model_name}")
        return True
    except Exception as e:
        print(f"[!] Failed to configure Claude Code: {e}")
        return False


def configure_opencode(proxy_key: str = None, model_name: str = None, port: int = None) -> bool:
    """Configures OpenCode (~/.opencode/config.json) to use nimproxy."""
    user_home = os.path.expanduser("~")
    opencode_dir = os.path.join(user_home, ".opencode")
    settings_file = os.path.join(opencode_dir, "config.json")

    proxy_key = proxy_key or settings.PROXY_API_KEY
    model_name = model_name or settings.DEFAULT_MODEL
    port = port or settings.PORT

    try:
        os.makedirs(opencode_dir, exist_ok=True)
        data = {}
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if "providers" not in data or not isinstance(data["providers"], dict):
            data["providers"] = {}

        data["providers"]["nimproxy"] = {
            "type": "openai",
            "baseUrl": f"http://localhost:{port}/v1",
            "apiKey": proxy_key,
            "models": [model_name]
        }

        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"[OK] OpenCode successfully configured at {settings_file}!")
        print(f"     Provider : nimproxy (type: openai)")
        print(f"     Base URL : http://localhost:{port}/v1")
        print(f"     API Key  : {proxy_key[:8]}...")
        print(f"     Model    : {model_name}")
        return True
    except Exception as e:
        print(f"[!] Failed to configure OpenCode: {e}")
        return False


def handle_export_command(subargs: List[str]):
    """Handles `nimproxy export [opencode|codex|claude|cursor|openai]`."""
    proxy_key = settings.PROXY_API_KEY
    model_name = settings.DEFAULT_MODEL
    port = settings.PORT

    target = subargs[0].lower() if subargs else "all"

    if target in ("opencode", "open-code"):
        configure_opencode(proxy_key, model_name, port)
        return

    if target in ("claude", "claudecode"):
        configure_claude_code(proxy_key, model_name, port)
        return

    if target in ("codex", "openai", "cursor", "continue"):
        print("=" * 65)
        print(f" OpenAI Compatible Configuration ({target.upper()})")
        print("=" * 65)
        print(f" Base URL : http://localhost:{port}/v1")
        print(f" API Key  : {proxy_key}")
        print(f" Model    : {model_name}")
        print("=" * 65)
        return

    # Default / list all exports
    print("=" * 65)
    print("   nimproxy Export Configuration for AI Coding Tools")
    print("=" * 65)
    print("\n1. OpenCode (~/.opencode/config.json):")
    print("   Run: 'nimproxy export opencode' to auto-configure!")
    print(f"   Base URL : http://localhost:{port}/v1")
    print(f"   API Key  : {proxy_key}")

    print("\n2. Claude Code (~/.claude/settings.json):")
    print("   Run: 'nimproxy claude' or 'nimproxy export claude' to auto-configure!")
    print(f"   Base URL : http://localhost:{port}")
    print(f"   API Key  : {proxy_key}")

    print("\n3. Codex / Cursor / OpenAI Compatible Clients:")
    print("   Run: 'nimproxy export codex' to view details.")
    print(f"   OPENAI_BASE_URL = http://localhost:{port}/v1")
    print(f"   OPENAI_API_KEY  = {proxy_key}")
    print(f"   MODEL           = {model_name}")
    print("=" * 65)


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


def handle_model_command(subargs: List[str]):
    """Handles `nimproxy model` and `nimproxy model set <name>`."""
    cfg = load_config_data()
    keys = cfg.get("nvidia_api_keys", settings.NVIDIA_API_KEYS)

    if not subargs or subargs[0] == "list":
        current_m = settings.DEFAULT_MODEL
        print("=" * 65)
        print(f" Current Active Model: {current_m}")
        print("=" * 65)
        print("Fetching available models from NVIDIA NIM...")
        models = fetch_available_models(keys)
        if models:
            print("\nAvailable Models:")
            for idx, m in enumerate(models[:20], 1):
                cur_tag = " [ACTIVE]" if m == current_m else ""
                print(f"  {idx}. {m}{cur_tag}")
            print(f"\nTo switch active model, run: nimproxy model set <model_name>")
        else:
            print("[!] Could not fetch model list from NVIDIA NIM.")
        return

    if subargs[0] == "set" and len(subargs) >= 2:
        new_model = subargs[1].strip()
        cfg["default_model"] = new_model
        save_config_data(cfg)
        print(f"[OK] Active model updated to: {new_model}")
        
        configure_claude_code(model_name=new_model)

        running, _ = is_server_running()
        if running:
            print("Restarting background server to apply changes...")
            restart_background_server()
        return

    print("Usage: nimproxy model | nimproxy model set <model_name>")


def handle_key_command(subargs: List[str]):
    """Handles `nimproxy key` (add, remove, list)."""
    cfg = load_config_data()
    keys = cfg.get("nvidia_api_keys", [])

    if not subargs or subargs[0] in ("list", "ls"):
        print("=" * 65)
        print(f" Configured NVIDIA NIM API Keys ({len(keys)} total):")
        print("=" * 65)
        for idx, k in enumerate(keys, 1):
            masked = f"{k[:4]}...{k[-4:]}" if len(k) > 8 else "***"
            print(f"  {idx}. Key: {masked}")
        print("=" * 65)
        print("Commands: nimproxy key add <api_key> | nimproxy key remove <index_or_key>")
        return

    if subargs[0] == "add" and len(subargs) >= 2:
        new_key = subargs[1].strip()
        if new_key in keys:
            print("[!] Key already exists in pool.")
            return
        keys.append(new_key)
        cfg["nvidia_api_keys"] = keys
        save_config_data(cfg)
        masked = f"{new_key[:4]}...{new_key[-4:]}" if len(new_key) > 8 else "***"
        print(f"[OK] Added API Key {masked} to pool. Total keys: {len(keys)}")

        running, _ = is_server_running()
        if running:
            restart_background_server()
        return

    if subargs[0] in ("remove", "rm", "delete") and len(subargs) >= 2:
        target = subargs[1].strip()
        removed = False
        if target.isdigit():
            idx = int(target) - 1
            if 0 <= idx < len(keys):
                rem_k = keys.pop(idx)
                removed = True
        else:
            if target in keys:
                keys.remove(target)
                removed = True

        if removed:
            if len(keys) == 0:
                print("[!] Warning: All API keys removed. nimproxy requires at least 1 key to run.")
            cfg["nvidia_api_keys"] = keys
            save_config_data(cfg)
            print(f"[OK] Key removed. Remaining keys: {len(keys)}")

            running, _ = is_server_running()
            if running:
                restart_background_server()
        else:
            print(f"[!] Key or index '{target}' not found in pool.")
        return

    print("Usage: nimproxy key list | nimproxy key add <key> | nimproxy key remove <index_or_key>")


def run_live_stats_dashboard():
    """Runs a real-time terminal stats dashboard with 1000ms polling and 'q' to quit."""
    running, health = is_server_running()
    if not running:
        print("[!] nimproxy server is not running. Starting background process...")
        start_background_server()
        time.sleep(1)

    print("Initializing Live Stats Dashboard... (Press 'q' at any time to exit)\n")
    time.sleep(0.5)

    def is_q_pressed() -> bool:
        if sys.platform == "win32":
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                if ch.lower() in (b'q', b'\x03'):
                    return True
        return False

    try:
        while True:
            running, health = is_server_running()
            pid = load_server_pid()

            if sys.platform == "win32":
                os.system("cls")
            else:
                print("\033[H\033[J", end="")

            print("=" * 67)
            print("   NVIDIA NIM Proxy Manager - Live Dashboard (1000ms Refresh)")
            print("=" * 67)
            
            if running and health:
                key_mgr = health.get("key_manager", {})
                total_keys = key_mgr.get("total_keys", 0)
                active_keys = key_mgr.get("active_keys", 0)
                model = health.get("default_model", settings.DEFAULT_MODEL)
                proxy_key = settings.PROXY_API_KEY

                total_reqs = sum(k.get("total_requests", 0) for k in key_mgr.get("keys", []))

                print(f" Status           : ONLINE (PID {pid or 'running'})")
                print(f" Version          : v{APP_VERSION}")
                print(f" Active Model     : {model}")
                print(f" Master Proxy Key : {proxy_key}")
                print(f" Endpoints        : OpenAI: http://localhost:{settings.PORT}/v1")
                print(f"                    Anthropic: http://localhost:{settings.PORT}")
                print("-------------------------------------------------------------------")
                print(" KEY POOL REAL-TIME STATUS:")
                for k in key_mgr.get("keys", []):
                    k_masked = k.get("key")
                    k_status = k.get("status", "active").upper()
                    reqs = k.get("total_requests", 0)
                    errs = k.get("429_errors", 0)
                    print(f"   - Key {k_masked:<16} | Status: {k_status:<12} | Reqs: {reqs:<5} | 429 Errors: {errs}")
                print("-------------------------------------------------------------------")
                print(f" TOTAL METRICS    : Active Keys: {active_keys}/{total_keys} | Total Served Requests: {total_reqs}")
            else:
                print(" Status           : OFFLINE (Server not responding)")
            
            print("=" * 67)
            print(" [Press 'q' or Ctrl+C to exit live dashboard and return to terminal]")

            for _ in range(10):
                if is_q_pressed():
                    print("\n\n[OK] Exited live stats dashboard.")
                    return
                time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n[OK] Exited live stats dashboard.")


def run_interactive_setup():
    """Guided terminal setup flow."""
    print("=" * 65)
    print(f"   NVIDIA NIM API Proxy Manager - Guided Setup (v{APP_VERSION})")
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
        display_models = []
        if recommended_model in fetched_models:
            display_models.append(recommended_model)
            for m in fetched_models:
                if m != recommended_model:
                    display_models.append(m)
        else:
            display_models = [recommended_model] + fetched_models

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
            if choice in fetched_models:
                selected_model = choice
            else:
                selected_model = recommended_model
    else:
        print(f"[!] Could not fetch model list from NVIDIA NIM. Using default recommended: {recommended_model}")

    print(f"\n[OK] Selected Model: {selected_model}")

    # Step 4: Claude Code & OpenCode Auto Configuration
    print("\n--- Step 3: AI Coding Tools Integration ---")
    claude_str = input("Configure Claude Code (~/.claude/settings.json)? [Y/n]: ").strip().lower()
    setup_claude = claude_str != 'n'

    opencode_str = input("Configure OpenCode (~/.opencode/config.json)? [Y/n]: ").strip().lower()
    setup_opencode = opencode_str != 'n'

    # Step 5: Master Proxy Key
    existing_config = load_config_data()
    proxy_key = existing_config.get("proxy_api_key")
    if not proxy_key:
        import secrets
        proxy_key = f"sk-nim-{secrets.token_hex(16)}"

    # Step 6: Save Config
    config_data = {
        "proxy_api_key": proxy_key,
        "nvidia_api_keys": keys,
        "default_model": selected_model,
        "nvidia_base_url": settings.NVIDIA_BASE_URL,
        "probe_interval_seconds": 30,
        "autostart_windows": autostart,
        "host": "0.0.0.0",
        "port": settings.PORT,
        "version": APP_VERSION
    }
    save_config_data(config_data)
    set_windows_autostart(autostart)

    if setup_claude:
        print()
        configure_claude_code(proxy_key, selected_model, settings.PORT)

    if setup_opencode:
        print()
        configure_opencode(proxy_key, selected_model, settings.PORT)

    # Step 7: Start Server in Background
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
    print(f" OpenAI Endpoint     : http://localhost:{settings.PORT}/v1")
    print(f" Anthropic Endpoint  : http://localhost:{settings.PORT}")
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
    print(" Commands: 'nimproxy export [opencode|codex|claude]' | 'nimproxy stats'")


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
    if "--help" in args or "-h" in args or "help" in args:
        print(f"""
=================================================================
   NVIDIA NIM API Proxy Manager CLI (nimproxy v{APP_VERSION})
=================================================================

Usage:
  nimproxy                  Display server status report or auto-start server
  nimproxy export [target]  Export config or auto-configure (opencode, codex, claude)
  nimproxy stats            Launch real-time live stats dashboard (1000ms polling, 'q' to exit)
  nimproxy model [set <name>] Manage active model or switch model instantly
  nimproxy key [add|remove|list] Manage API Key pool dynamically
  nimproxy start            Start background server process
  nimproxy stop             Stop background server process
  nimproxy restart          Restart background server process
  nimproxy setup / config   Run interactive guided setup wizard
  nimproxy claude           Auto-configure Claude Code (~/.claude/settings.json)
  nimproxy update           Check GitHub releases for updates
  nimproxy version          Show current version

Options:
  -h, --help                Show this help message and exit
  -v, --version             Show version number

Examples:
  nimproxy export opencode  Auto-configures OpenCode (~/.opencode/config.json)
  nimproxy export codex     Shows OpenAI compatible settings for Codex / Cursor
  nimproxy stats            Opens live terminal dashboard with 1s refresh
=================================================================
""")
        return

    if "--setup" in args or "setup" in args or "config" in args:
        run_interactive_setup()
        return

    if "export" in args:
        idx = args.index("export")
        handle_export_command(args[idx + 1:])
        return

    if "stats" in args or "dashboard" in args:
        run_live_stats_dashboard()
        return

    if "model" in args:
        idx = args.index("model")
        handle_model_command(args[idx + 1:])
        return

    if "key" in args or "keys" in args:
        idx = args.index("key") if "key" in args else args.index("keys")
        handle_key_command(args[idx + 1:])
        return

    if "claude" in args:
        print("Configuring Claude Code settings...")
        configure_claude_code()
        return

    if "stop" in args:
        print("Stopping nimproxy background server...")
        if stop_background_server():
            print("[OK] Server stopped successfully.")
        else:
            print("[!] Server was not running.")
        return

    if "restart" in args:
        print("Restarting nimproxy background server...")
        stop_background_server()
        time.sleep(1)
        if start_background_server():
            print("[OK] Server restarted successfully.")
        else:
            print("[ERRO] Failed to restart server.")
        return

    if "update" in args:
        print(f"Checking for updates (Current version: v{APP_VERSION})...")
        if not check_for_updates():
            print("[OK] nimproxy is already on the latest version!")
        return

    if "version" in args or "--version" in args or "-v" in args:
        print(f"nimproxy v{APP_VERSION}")
        return

    # Default action (typing 'nimproxy')
    if not settings.NVIDIA_API_KEYS:
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
                print(f"[OK] nimproxy server started successfully in background on port {settings.PORT}!")
        else:
            print("[ERRO] Failed to start nimproxy server in background.")


if __name__ == "__main__":
    main()
