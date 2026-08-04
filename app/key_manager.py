import time
import asyncio
import threading
import httpx
from typing import List, Dict, Optional

from app.logger import logger
from app.config import settings


class AllKeysExhaustedException(Exception):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(
            f"Todas as API Keys ativas estão em Rate Limit (HTTP 429) no modelo {settings.DEFAULT_MODEL}! "
            f"Sondagens em andamento a cada {settings.PROBE_INTERVAL_SECONDS}s."
        )


class AllKeysInvalidException(Exception):
    def __init__(self, message: str):
        super().__init__(message)


class KeyInfo:
    def __init__(self, key: str):
        self.key = key
        self.is_rate_limited: bool = False
        self.is_invalid: bool = False
        self.invalid_reason: str = ""
        self.last_429_time: float = 0.0
        self.last_probe_time: float = 0.0
        self.probe_in_progress: bool = False
        self.total_requests: int = 0
        self.success_requests: int = 0
        self.rate_limit_429_count: int = 0

    @property
    def masked_key(self) -> str:
        if len(self.key) <= 8:
            return "***"
        return f"{self.key[:4]}...{self.key[-4:]}"

    @property
    def status(self) -> str:
        if self.is_invalid:
            return "invalid"
        elif self.is_rate_limited:
            return "rate_limited"
        return "active"


def _build_probe_payload() -> Dict:
    """Payload de 1 token extremamente leve para testar o modelo específico."""
    return {
        "model": settings.DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "temperature": 0.0
    }


async def probe_key_task(key_info: KeyInfo, base_url: str, interval: int, key_manager_ref):
    """
    Sonda silenciosamente a chave em Rate Limit especificamente para o modelo configurado (ex: z-ai/glm-5.2).
    Assim que retornar 200, altera is_rate_limited para False.
    """
    key_info.probe_in_progress = True
    masked = key_info.masked_key

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key_info.key}",
        "Content-Type": "application/json"
    }
    payload = _build_probe_payload()

    try:
        while key_info.is_rate_limited and not key_info.is_invalid:
            await asyncio.sleep(interval)
            key_info.last_probe_time = time.time()

            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    resp = await client.post(url, json=payload, headers=headers)
                    if resp.status_code == 200:
                        key_info.is_rate_limited = False
                        logger.info(
                            f"[KeyManager] Key {masked} voltou a responder HTTP 200 OK para o modelo {settings.DEFAULT_MODEL}. Saiu do Rate Limit!"
                        )
                        break
                    elif resp.status_code in (401, 403):
                        key_manager_ref.mark_invalid(key_info.key, f"HTTP {resp.status_code} na sondagem")
                        break
                except Exception:
                    pass
    finally:
        key_info.probe_in_progress = False


class KeyManager:
    def __init__(self, keys: List[str] = None):
        self._lock = threading.Lock()
        self._keys: List[KeyInfo] = []
        self._current_index = 0
        if keys:
            self.set_keys(keys)

    def set_keys(self, keys: List[str]):
        with self._lock:
            self._keys = [KeyInfo(k) for k in keys if k]
            self._current_index = 0
            logger.info(f"[KeyManager] Inicializado com {len(self._keys)} API Key(s).")

    def get_next_key(self) -> str:
        with self._lock:
            if not self._keys:
                raise ValueError("Nenhuma NVIDIA API Key foi configurada no sistema (.env).")

            valid_keys = [k for k in self._keys if not k.is_invalid]
            if not valid_keys:
                logger.error("[KeyManager] TODAS AS KEYS FORAM DESCARTADAS POR SEREM INVÁLIDAS / NÃO AUTORIZADAS (401/403).")
                raise AllKeysInvalidException("Todas as API Keys configuradas são inválidas ou incompatíveis.")

            num_keys = len(self._keys)
            for _ in range(num_keys):
                candidate = self._keys[self._current_index]
                self._current_index = (self._current_index + 1) % num_keys

                if not candidate.is_invalid and not candidate.is_rate_limited:
                    candidate.total_requests += 1
                    return candidate.key

            logger.error(
                f"[KeyManager] TODAS AS KEYS VÁLIDAS ESTÃO EM RATE LIMIT (429) PARA {settings.DEFAULT_MODEL}! "
                f"Sondagens ativas a cada {settings.PROBE_INTERVAL_SECONDS}s em andamento."
            )
            raise AllKeysExhaustedException(retry_after=float(settings.PROBE_INTERVAL_SECONDS))

    def mark_429(self, key: str):
        with self._lock:
            now = time.time()
            for k in self._keys:
                if k.key == key and not k.is_invalid:
                    k.is_rate_limited = True
                    k.last_429_time = now
                    k.rate_limit_429_count += 1
                    logger.warning(
                        f"[KeyManager] Key {k.masked_key} recebeu HTTP 429 para {settings.DEFAULT_MODEL}. Rotacionando automaticamente..."
                    )
                    if not k.probe_in_progress:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(probe_key_task(k, settings.NVIDIA_BASE_URL, settings.PROBE_INTERVAL_SECONDS, self))
                        except RuntimeError:
                            pass
                    break

    def mark_invalid(self, key: str, reason: str = "Key inválida/incompatível"):
        with self._lock:
            for k in self._keys:
                if k.key == key:
                    k.is_invalid = True
                    k.invalid_reason = reason
                    active_count = sum(1 for x in self._keys if not x.is_invalid and not x.is_rate_limited)
                    logger.error(
                        f"[KeyManager] SEGURANÇA: Key {k.masked_key} é INVÁLIDA/INCOMPATÍVEL ({reason}). "
                        f"Descartada para esta sessão! Chaves ativas restantes: {active_count}/{len(self._keys)}"
                    )
                    break

    def mark_success(self, key: str):
        with self._lock:
            for k in self._keys:
                if k.key == key:
                    k.success_requests += 1
                    break

    def get_status(self) -> Dict:
        with self._lock:
            key_stats = []
            for k in self._keys:
                key_stats.append({
                    "key": k.masked_key,
                    "status": k.status,
                    "is_rate_limited": k.is_rate_limited,
                    "is_invalid": k.is_invalid,
                    "invalid_reason": k.invalid_reason,
                    "total_requests": k.total_requests,
                    "success_requests": k.success_requests,
                    "429_errors": k.rate_limit_429_count
                })
            return {
                "total_keys": len(self._keys),
                "active_keys": sum(1 for k in self._keys if not k.is_invalid and not k.is_rate_limited),
                "rate_limited_keys": sum(1 for k in self._keys if k.is_rate_limited and not k.is_invalid),
                "invalid_keys": sum(1 for k in self._keys if k.is_invalid),
                "keys": key_stats
            }


key_manager = KeyManager(settings.NVIDIA_API_KEYS)


async def verify_keys_on_startup(base_url: str):
    """
    Testa todas as chaves no startup do servidor diretamente contra o modelo configurado (z-ai/glm-5.2)
    usando um teste ultra-leve de 1 token para validar rate-limit exato por modelo.
    """
    keys = key_manager._keys
    if not keys:
        logger.warning("[StartupCheck] Nenhuma chave configurada para testar.")
        return

    logger.info(f"VERIFICAÇÃO DE INICIALIZAÇÃO DAS KEYS (Modelo: {settings.DEFAULT_MODEL}):")
    url = f"{base_url}/chat/completions"
    payload = _build_probe_payload()

    async with httpx.AsyncClient(timeout=10.0) as client:
        for k in keys:
            headers = {
                "Authorization": f"Bearer {k.key}",
                "Content-Type": "application/json"
            }
            try:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    k.is_rate_limited = False
                    k.is_invalid = False
                    logger.info(f"   [OK] Key {k.masked_key} -> ATIVA E PRONTA PARA {settings.DEFAULT_MODEL} (HTTP 200)")
                elif resp.status_code == 429:
                    k.is_rate_limited = True
                    logger.warning(f"   [WARNING] Key {k.masked_key} -> RATE LIMITED (HTTP 429) no modelo {settings.DEFAULT_MODEL} - Sondagem ativa agendada")
                    if not k.probe_in_progress:
                        try:
                            loop = asyncio.get_running_loop()
                            loop.create_task(probe_key_task(k, base_url, settings.PROBE_INTERVAL_SECONDS, key_manager))
                        except RuntimeError:
                            pass
                elif resp.status_code in (401, 403):
                    k.is_invalid = True
                    k.invalid_reason = f"HTTP {resp.status_code}"
                    logger.error(f"   [ERRO] Key {k.masked_key} -> INVÁLIDA/NÃO AUTORIZADA (HTTP {resp.status_code}) - Descartada")
                else:
                    logger.warning(f"   [?] Key {k.masked_key} -> Respondeu status {resp.status_code}")
            except Exception as exc:
                logger.error(f"   [ERRO] Key {k.masked_key} -> Falha de conexão no teste inicial: {exc}")

    status = key_manager.get_status()
    logger.info(f"   STATUS FINAL: {status['active_keys']}/{status['total_keys']} Keys Ativas e Prontas para Uso!")
