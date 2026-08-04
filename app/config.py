import os
import re
import secrets
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()


class Settings:
    def __init__(self):
        self._proxy_api_key = None

    @property
    def PROXY_API_KEY(self) -> str:
        if self._proxy_api_key:
            return self._proxy_api_key

        key = os.getenv("PROXY_API_KEY", "").strip()
        if not key:
            # Generate a secure master key for the proxy
            key = f"sk-nim-{secrets.token_hex(16)}"
            self._proxy_api_key = key

            # Append the generated key to .env file for persistence
            env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
            try:
                if os.path.exists(env_path):
                    with open(env_path, "a", encoding="utf-8") as f:
                        f.write(f"\n# Auto-generated Proxy Master API Key\nPROXY_API_KEY={key}\n")
                else:
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(f"PROXY_API_KEY={key}\n")
                print(f"[Config] Generated new PROXY_API_KEY saved to .env: {key}")
            except Exception as e:
                print(f"[Config] Warning: Failed to write PROXY_API_KEY to .env: {e}")
        else:
            self._proxy_api_key = key

        return self._proxy_api_key

    @property
    def NVIDIA_API_KEYS(self) -> List[str]:
        keys = []

        # 1. Search for individual numbered environment variables (NVIDIA_API_KEY_1, NVIDIA_API_KEY_2, etc.)
        env_vars = sorted([var for var in os.environ if var.startswith("NVIDIA_API_KEY_")])
        for var in env_vars:
            val = os.getenv(var, "").strip()
            if val and val not in keys:
                keys.append(val)

        # 2. Search for NVIDIA_API_KEYS (supports multiline or comma-separated keys)
        raw_keys_str = os.getenv("NVIDIA_API_KEYS", "")
        if raw_keys_str:
            split_keys = [k.strip() for k in re.split(r"[\n,\r]+", raw_keys_str) if k.strip()]
            for k in split_keys:
                if k not in keys:
                    keys.append(k)

        # 3. Single NVIDIA_API_KEY support
        single_key = os.getenv("NVIDIA_API_KEY")
        if single_key and single_key.strip() and single_key.strip() not in keys:
            keys.append(single_key.strip())

        return keys

    @property
    def DEFAULT_MODEL(self) -> str:
        return os.getenv("DEFAULT_MODEL", "z-ai/glm-5.2")

    @property
    def NVIDIA_BASE_URL(self) -> str:
        return os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")

    @property
    def COOLDOWN_SECONDS(self) -> int:
        return int(os.getenv("COOLDOWN_SECONDS", "60"))

    @property
    def PROBE_INTERVAL_SECONDS(self) -> int:
        return int(os.getenv("PROBE_INTERVAL_SECONDS", "30"))

    @property
    def HOST(self) -> str:
        return os.getenv("HOST", "0.0.0.0")

    @property
    def PORT(self) -> int:
        return int(os.getenv("PORT", "8000"))


settings = Settings()
