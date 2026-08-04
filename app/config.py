import os
import re
import json
import secrets
from typing import List, Dict, Any
from dotenv import load_dotenv

APP_VERSION = "0.3.1"
DEFAULT_PORT = 43100

def get_app_dir() -> str:
    """Returns the application data directory (%APPDATA%\\nimproxy or local root)."""
    appdata = os.getenv("APPDATA")
    if appdata:
        target_dir = os.path.join(appdata, "nimproxy")
        if os.path.exists(target_dir):
            return target_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_config_file_path() -> str:
    return os.path.join(get_app_dir(), "config.json")


def load_config_data() -> Dict[str, Any]:
    config_path = get_config_file_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config_data(data: Dict[str, Any]):
    config_dir = get_app_dir()
    os.makedirs(config_dir, exist_ok=True)
    config_path = get_config_file_path()
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Load environment variables from .env file if present
load_dotenv()


class Settings:
    def __init__(self):
        self._proxy_api_key = None

    @property
    def VERSION(self) -> str:
        return APP_VERSION

    @property
    def PROXY_API_KEY(self) -> str:
        cfg = load_config_data()
        if cfg.get("proxy_api_key"):
            return cfg["proxy_api_key"]

        if self._proxy_api_key:
            return self._proxy_api_key

        key = os.getenv("PROXY_API_KEY", "").strip()
        if not key:
            key = f"sk-nim-{secrets.token_hex(16)}"
            self._proxy_api_key = key
            
            # Save to config.json or .env
            cfg["proxy_api_key"] = key
            save_config_data(cfg)
        else:
            self._proxy_api_key = key

        return self._proxy_api_key

    @property
    def NVIDIA_API_KEYS(self) -> List[str]:
        cfg = load_config_data()
        if cfg.get("nvidia_api_keys") and isinstance(cfg["nvidia_api_keys"], list):
            return [k.strip() for k in cfg["nvidia_api_keys"] if k.strip()]

        keys = []
        env_vars = sorted([var for var in os.environ if var.startswith("NVIDIA_API_KEY_")])
        for var in env_vars:
            val = os.getenv(var, "").strip()
            if val and val not in keys:
                keys.append(val)

        raw_keys_str = os.getenv("NVIDIA_API_KEYS", "")
        if raw_keys_str:
            split_keys = [k.strip() for k in re.split(r"[\n,\r]+", raw_keys_str) if k.strip()]
            for k in split_keys:
                if k not in keys:
                    keys.append(k)

        single_key = os.getenv("NVIDIA_API_KEY")
        if single_key and single_key.strip() and single_key.strip() not in keys:
            keys.append(single_key.strip())

        return keys

    @property
    def DEFAULT_MODEL(self) -> str:
        cfg = load_config_data()
        if cfg.get("default_model"):
            return cfg["default_model"]
        return os.getenv("DEFAULT_MODEL", "z-ai/glm-5.2")

    @property
    def NVIDIA_BASE_URL(self) -> str:
        cfg = load_config_data()
        if cfg.get("nvidia_base_url"):
            return cfg["nvidia_base_url"].rstrip("/")
        return os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")

    @property
    def COOLDOWN_SECONDS(self) -> int:
        cfg = load_config_data()
        if cfg.get("cooldown_seconds"):
            return int(cfg["cooldown_seconds"])
        return int(os.getenv("COOLDOWN_SECONDS", "60"))

    @property
    def PROBE_INTERVAL_SECONDS(self) -> int:
        cfg = load_config_data()
        if cfg.get("probe_interval_seconds"):
            return int(cfg["probe_interval_seconds"])
        return int(os.getenv("PROBE_INTERVAL_SECONDS", "30"))

    @property
    def HOST(self) -> str:
        cfg = load_config_data()
        if cfg.get("host"):
            return cfg["host"]
        return os.getenv("HOST", "0.0.0.0")

    @property
    def PORT(self) -> int:
        cfg = load_config_data()
        if cfg.get("port"):
            return int(cfg["port"])
        return int(os.getenv("PORT", str(DEFAULT_PORT)))


settings = Settings()
