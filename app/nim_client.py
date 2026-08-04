import json
import httpx
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from fastapi.responses import JSONResponse

from app.config import settings
from app.key_manager import key_manager, AllKeysExhaustedException, AllKeysInvalidException
from app.logger import logger
from app.anthropic_translator import format_sse

# Shared reusable Keep-Alive HTTP client pool
_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    """Returns the shared httpx.AsyncClient instance with reusable connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        limits = httpx.Limits(max_keepalive_connections=50, max_connections=200, keepalive_expiry=60.0)
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
        _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client


async def send_request_with_failover(payload: Dict[str, Any], stream: bool = False):
    """
    Sends request to NVIDIA NIM API using persistent connection pool.
    - If key gets 429 (Rate Limit), marks key and transparently rotates to next key.
    - If key gets 401/403 (Invalid/Unauthorized), discards key for current session and rotates.
    - If network error occurs, retries next key.
    """
    payload["model"] = settings.DEFAULT_MODEL
    url = f"{settings.NVIDIA_BASE_URL}/chat/completions"
    
    total_keys = key_manager.get_status()["total_keys"]
    attempts = 0

    while attempts < max(1, total_keys):
        attempts += 1
        try:
            current_key = key_manager.get_next_key()
        except AllKeysExhaustedException as exc:
            logger.error(f"[NIMClient] {exc}")
            status = key_manager.get_status()
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": f"All active API keys ({status['total_keys']}) are temporarily rate limited (HTTP 429).",
                        "type": "rate_limit_error",
                        "active_keys": status["active_keys"],
                        "total_keys": status["total_keys"],
                        "code": 429
                    }
                }
            )
        except AllKeysInvalidException as exc:
            logger.error(f"[NIMClient] {exc}")
            status = key_manager.get_status()
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "message": str(exc),
                        "type": "invalid_api_key_error",
                        "active_keys": status["active_keys"],
                        "invalid_keys": status["invalid_keys"],
                        "total_keys": status["total_keys"],
                        "code": 401
                    }
                }
            )

        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json"
        }

        masked_key = f"{current_key[:4]}...{current_key[-4:]}" if len(current_key) > 8 else "***"
        client = get_shared_client()

        try:
            if not stream:
                resp = await client.post(url, json=payload, headers=headers)
                
                # 1. Handle Rate Limit 429 (Silent Rotation)
                if resp.status_code == 429:
                    key_manager.mark_429(current_key)
                    continue

                # 2. Handle Invalid / Unauthorized Key (401 / 403)
                if resp.status_code in (401, 403):
                    key_manager.mark_invalid(current_key, f"HTTP {resp.status_code}")
                    continue

                # 3. Success (HTTP 200)
                if resp.status_code == 200:
                    key_manager.mark_success(current_key)
                    res_json = resp.json()

                    usage = res_json.get("usage", {})
                    p_tokens = usage.get("prompt_tokens", 0)
                    c_tokens = usage.get("completion_tokens", 0)
                    t_tokens = usage.get("total_tokens", p_tokens + c_tokens)
                    
                    logger.info(
                        f"[API] POST /v1/chat/completions - Status 200 - Key {masked_key} - "
                        f"Model: {payload.get('model')} - Tokens: {p_tokens} prompt, {c_tokens} completion (Total: {t_tokens})"
                    )
                    return res_json
                else:
                    logger.error(f"[API] HTTP Error {resp.status_code} from NVIDIA NIM (Key {masked_key}): {resp.text}")
                    content = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error": resp.text}
                    return JSONResponse(status_code=resp.status_code, content=content)

            else:
                # Streaming (stream=True)
                req = client.build_request("POST", url, json=payload, headers=headers)
                resp = await client.send(req, stream=True)

                if resp.status_code == 429:
                    await resp.aclose()
                    key_manager.mark_429(current_key)
                    continue

                if resp.status_code in (401, 403):
                    await resp.aclose()
                    key_manager.mark_invalid(current_key, f"HTTP {resp.status_code}")
                    continue

                if resp.status_code != 200:
                    content = await resp.aread()
                    await resp.aclose()
                    logger.error(f"[API] HTTP Error {resp.status_code} in streaming (Key {masked_key}): {content.decode('utf-8')}")
                    return JSONResponse(status_code=resp.status_code, content={"error": content.decode('utf-8')})

                key_manager.mark_success(current_key)
                logger.info(f"[API] POST /v1/chat/completions (Stream) - Connection established - Key {masked_key} - Model: {payload.get('model')}")
                return resp, None

        except httpx.RequestError as exc:
            err_name = type(exc).__name__
            err_msg = str(exc) or "Timeout / Connection reset by peer"
            logger.error(f"[API] Network connection error with Key {masked_key}: {err_name} ({err_msg})")
            continue

    # All attempts failed
    status = key_manager.get_status()
    logger.error(f"[API] No keys available to fulfill request. Status: {status}")
    return JSONResponse(
        status_code=429 if status["active_keys"] == 0 and status["rate_limited_keys"] > 0 else 401,
        content={
            "error": {
                "message": "No valid or active API key available in proxy.",
                "type": "no_available_keys_error",
                "active_keys": status["active_keys"],
                "rate_limited_keys": status["rate_limited_keys"],
                "invalid_keys": status["invalid_keys"],
                "total_keys": status["total_keys"]
            }
        }
    )


async def stream_openai_response(resp: httpx.Response, unused_client=None) -> AsyncGenerator[bytes, None]:
    """Streams native OpenAI SSE events while preserving connection pool."""
    try:
        async for chunk in resp.aiter_bytes():
            yield chunk
    except Exception as exc:
        logger.error(f"[StreamOpenAI] Interruption in streaming: {type(exc).__name__} ({exc})")
    finally:
        await resp.aclose()


async def stream_anthropic_response(resp: httpx.Response, unused_client=None, model_name: str = "") -> AsyncGenerator[str, None]:
    """Converts native OpenAI stream to Anthropic SSE event sequence (Claude Code)."""
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    
    yield format_sse("message_start", {
        "type": "message_start",
        "message": {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": model_name,
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0}
        }
    })

    yield format_sse("content_block_start", {
        "type": "content_block_start",
        "index": 0,
        "content_block": {"type": "text", "text": ""}
    })

    yield format_sse("ping", {"type": "ping"})

    total_tokens = 0

    try:
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            lines = buffer.split("\n")
            buffer = lines.pop()

            for line in lines:
                line = line.strip()
                if not line or line.startswith(":"):
                    continue

                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content_text = delta.get("content")
                            if content_text:
                                total_tokens += 1
                                yield format_sse("content_block_delta", {
                                    "type": "content_block_delta",
                                    "index": 0,
                                    "delta": {"type": "text_delta", "text": content_text}
                                })
                    except Exception:
                        pass
    except Exception as exc:
        logger.error(f"[StreamAnthropic] Interruption in streaming: {type(exc).__name__} ({exc})")
    finally:
        await resp.aclose()

    yield format_sse("content_block_stop", {"type": "content_block_stop", "index": 0})
    yield format_sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": total_tokens}
    })
    yield format_sse("message_stop", {"type": "message_stop"})
