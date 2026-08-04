import json
import uuid
import httpx
from typing import Dict, Any, Tuple, Optional, AsyncGenerator
from starlette.responses import JSONResponse

from app.logger import logger
from app.config import settings
from app.key_manager import key_manager
from app.anthropic_translator import format_sse

# Global HTTP AsyncClient Pool
_shared_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    """
    Returns a singleton HTTP AsyncClient with high-performance connection pooling.
    Keeps TCP/TLS connections alive to NVIDIA NIM endpoints.
    Uses strict 15s read timeout to failover rapidly to alternative keys if one key hangs.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            limits=httpx.Limits(
                max_keepalive_connections=50,
                max_connections=200,
                keepalive_expiry=60.0
            ),
            timeout=httpx.Timeout(timeout=15.0, connect=5.0, read=15.0),
            trust_env=False,
            http2=False
        )
    return _shared_client


async def send_request_with_failover(payload: Dict[str, Any], stream: bool = False) -> Tuple[Any, Any]:
    """
    Sends request to NVIDIA NIM with automatic failover on HTTP 429 (Rate Limit) or timeouts.
    Tries active keys in round-robin order until success or exhaustion.
    """
    client = get_shared_client()
    url = f"{settings.NVIDIA_BASE_URL}/chat/completions"

    total_keys = len(key_manager._keys)
    attempts = 0

    while attempts < total_keys:
        attempts += 1
        try:
            current_key = key_manager.get_next_key()
        except Exception as exc:
            logger.error(f"[API] Cannot fetch next key: {exc}")
            status = key_manager.get_status()
            return JSONResponse(
                status_code=429 if status["active_keys"] == 0 and status["rate_limited_keys"] > 0 else 401,
                content={
                    "error": {
                        "message": str(exc),
                        "type": "all_keys_unavailable",
                        "active_keys": status["active_keys"],
                        "rate_limited_keys": status["rate_limited_keys"],
                        "invalid_keys": status["invalid_keys"]
                    }
                }
            )

        masked_key = f"{current_key[:4]}...{current_key[-4:]}" if len(current_key) > 8 else "***"
        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        try:
            if not stream:
                resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 429:
                    key_manager.mark_429(current_key)
                    continue

                if resp.status_code in (401, 403):
                    key_manager.mark_invalid(current_key, f"HTTP {resp.status_code}")
                    continue

                if resp.status_code != 200:
                    logger.error(f"[API] HTTP Error {resp.status_code} (Key {masked_key}): {resp.text}")
                    return JSONResponse(status_code=resp.status_code, content=resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"error": resp.text})

                key_manager.mark_success(current_key)
                return resp.json()

            else:
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

        except (httpx.RequestError, httpx.TimeoutException) as exc:
            err_name = type(exc).__name__
            err_msg = str(exc) or "Timeout / Connection reset by peer"
            logger.warning(f"[API] Key {masked_key} connection timeout/error ({err_name}: {err_msg}). Auto-rotating to next key...")
            key_manager.mark_429(current_key)
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

    yield format_sse("ping", {"type": "ping"})

    total_tokens = 0
    current_block_index = -1
    text_block_started = False
    active_tool_blocks = {}  # tool_index -> {block_index, id, name}
    final_stop_reason = "end_turn"

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
                        if not choices:
                            continue
                        
                        choice = choices[0]
                        finish_reason = choice.get("finish_reason")
                        if finish_reason == "tool_calls":
                            final_stop_reason = "tool_use"
                        elif finish_reason == "length":
                            final_stop_reason = "max_tokens"

                        delta = choice.get("delta", {})

                        # 1. Handle Text Delta
                        content_text = delta.get("content")
                        if content_text:
                            total_tokens += 1
                            if not text_block_started:
                                current_block_index += 1
                                text_block_started = True
                                yield format_sse("content_block_start", {
                                    "type": "content_block_start",
                                    "index": current_block_index,
                                    "content_block": {"type": "text", "text": ""}
                                })

                            yield format_sse("content_block_delta", {
                                "type": "content_block_delta",
                                "index": current_block_index,
                                "delta": {"type": "text_delta", "text": content_text}
                            })

                        # 2. Handle Tool Call Delta
                        tool_calls = delta.get("tool_calls", [])
                        for tc in tool_calls:
                            tc_idx = tc.get("index", 0)
                            tc_id = tc.get("id")
                            func = tc.get("function", {})
                            fn_name = func.get("name")
                            fn_args_delta = func.get("arguments", "")

                            if tc_idx not in active_tool_blocks:
                                if text_block_started:
                                    yield format_sse("content_block_stop", {"type": "content_block_stop", "index": current_block_index})
                                    text_block_started = False

                                current_block_index += 1
                                tool_id = tc_id or f"toolu_{uuid.uuid4().hex[:8]}"
                                active_tool_blocks[tc_idx] = {
                                    "block_index": current_block_index,
                                    "id": tool_id,
                                    "name": fn_name or ""
                                }
                                yield format_sse("content_block_start", {
                                    "type": "content_block_start",
                                    "index": current_block_index,
                                    "content_block": {
                                        "type": "tool_use",
                                        "id": tool_id,
                                        "name": fn_name or "",
                                        "input": {}
                                    }
                                })

                            blk_info = active_tool_blocks[tc_idx]
                            if fn_args_delta:
                                total_tokens += 1
                                yield format_sse("content_block_delta", {
                                    "type": "content_block_delta",
                                    "index": blk_info["block_index"],
                                    "delta": {
                                        "type": "input_json_delta",
                                        "partial_json": fn_args_delta
                                    }
                                })

                    except Exception:
                        pass
    except Exception as exc:
        logger.error(f"[StreamAnthropic] Interruption in streaming: {type(exc).__name__} ({exc})")
    finally:
        await resp.aclose()

    # Close open content blocks
    if text_block_started:
        yield format_sse("content_block_stop", {"type": "content_block_stop", "index": current_block_index})
    for tc_idx, blk in active_tool_blocks.items():
        yield format_sse("content_block_stop", {"type": "content_block_stop", "index": blk["block_index"]})

    if active_tool_blocks and final_stop_reason == "end_turn":
        final_stop_reason = "tool_use"

    yield format_sse("message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": final_stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": total_tokens}
    })
    yield format_sse("message_stop", {"type": "message_stop"})
