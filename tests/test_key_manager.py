import asyncio
import pytest
from app.key_manager import KeyManager, AllKeysExhaustedException, AllKeysInvalidException, probe_key_task


def test_key_manager_single_key():
    km = KeyManager(["nvapi-key1"])
    assert km.get_next_key() == "nvapi-key1"
    assert km.get_next_key() == "nvapi-key1"


def test_key_manager_round_robin():
    km = KeyManager(["nvapi-key1", "nvapi-key2", "nvapi-key3"])
    assert km.get_next_key() == "nvapi-key1"
    assert km.get_next_key() == "nvapi-key2"
    assert km.get_next_key() == "nvapi-key3"
    assert km.get_next_key() == "nvapi-key1"


def test_key_manager_failover_is_rate_limited():
    km = KeyManager(["nvapi-key1", "nvapi-key2"])
    
    k1 = km.get_next_key()
    assert k1 == "nvapi-key1"

    km.mark_429("nvapi-key1")

    status = km.get_status()
    assert status["rate_limited_keys"] == 1
    assert status["keys"][0]["is_rate_limited"] is True

    assert km.get_next_key() == "nvapi-key2"
    assert km.get_next_key() == "nvapi-key2"


def test_key_manager_invalid_key_discard():
    """Testa se uma chave marcada como inválida é descartada para a sessão."""
    km = KeyManager(["nvapi-key1", "nvapi-key2"])
    
    # Marca key1 como inválida (401/403)
    km.mark_invalid("nvapi-key1", "HTTP 401 Unauthorized")
    
    status = km.get_status()
    assert status["invalid_keys"] == 1
    assert status["active_keys"] == 1
    assert status["keys"][0]["status"] == "invalid"

    # A próxima chamada deve ignorar a key1 e usar key2
    assert km.get_next_key() == "nvapi-key2"
    assert km.get_next_key() == "nvapi-key2"


def test_all_keys_invalid_exception():
    km = KeyManager(["nvapi-key1", "nvapi-key2"])
    km.mark_invalid("nvapi-key1", "HTTP 401")
    km.mark_invalid("nvapi-key2", "HTTP 401")

    # Ambas inválidas -> deve disparar AllKeysInvalidException
    with pytest.raises(AllKeysInvalidException) as exc_info:
        km.get_next_key()

    assert "todas" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_probe_reactivation(monkeypatch):
    """Testa se a chave reativa (is_rate_limited=False) quando o probe recebe HTTP 200."""
    km = KeyManager(["nvapi-key1"])
    key_info = km._keys[0]
    km.mark_429("nvapi-key1")
    assert key_info.is_rate_limited is True

    class MockResponse:
        status_code = 200
        text = "OK"

    class MockAsyncClient:
        def __init__(self, timeout=None):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def get(self, url, headers=None):
            return MockResponse()

    monkeypatch.setattr("httpx.AsyncClient", MockAsyncClient)

    asyncio.run(probe_key_task(key_info, "https://mock", interval=0.05, key_manager_ref=km))

    assert key_info.is_rate_limited is False
    assert km.get_next_key() == "nvapi-key1"
