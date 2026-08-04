import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Header
from starlette.responses import JSONResponse, StreamingResponse

from app.logger import logger
from app.config import settings
from app.key_manager import key_manager, verify_keys_on_startup
from app.nim_client import send_request_with_failover, stream_openai_response, stream_anthropic_response
from app.anthropic_translator import anthropic_request_to_openai, openai_response_to_anthropic


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler to execute lightweight 1-token key verification on startup.
    """
    logger.info(f"Starting NVIDIA NIM API Proxy v{settings.VERSION} on port {settings.PORT}...")
    try:
        asyncio.create_task(verify_keys_on_startup(settings.NVIDIA_BASE_URL))
    except Exception as e:
        logger.error(f"[StartupCheck] Error launching key verification: {e}")
    yield
    logger.info("Shutting down proxy server.")


app = FastAPI(
    title="NVIDIA NIM API Proxy Manager",
    version=settings.VERSION,
    description="Dual-protocol proxy (OpenAI & Anthropic Compatible) with key failover",
    lifespan=lifespan
)


def verify_proxy_auth(request: Request) -> bool:
    """
    Verifies authentication against PROXY_API_KEY.
    Supports both Authorization: Bearer <KEY> and x-api-key: <KEY> headers.
    """
    expected_key = settings.PROXY_API_KEY
    if not expected_key:
        return True

    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token == expected_key:
            return True

    x_api_key = request.headers.get("x-api-key", "").strip()
    if x_api_key == expected_key:
        return True

    return False


@app.api_route("/api/hello", methods=["GET", "HEAD"])
async def claude_code_healthcheck():
    """
    Endpoint queried by Claude Code on startup to test connectivity.
    """
    return JSONResponse(status_code=200, content={"status": "ok", "service": "nimproxy"})


@app.get("/health")
async def health_check():
    """Health check endpoint exposing server metrics and key manager status."""
    return {
        "status": "online",
        "version": settings.VERSION,
        "default_model": settings.DEFAULT_MODEL,
        "nvidia_base_url": settings.NVIDIA_BASE_URL,
        "key_manager": key_manager.get_status()
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """
    Native OpenAI compatible endpoint (POST /v1/chat/completions).
    """
    if not verify_proxy_auth(request):
        logger.warning("[Auth] Access denied on /v1/chat/completions: Invalid or missing PROXY_API_KEY.")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid or missing Proxy API Key. Provide PROXY_API_KEY in Authorization Bearer header.",
                    "type": "authentication_error",
                    "code": 401
                }
            }
        )

    try:
        body = await request.json()
    except Exception:
        body = {}

    is_stream = body.get("stream", False)
    result = await send_request_with_failover(body, stream=is_stream)

    if isinstance(result, JSONResponse):
        return result

    if is_stream:
        resp, client = result
        return StreamingResponse(
            stream_openai_response(resp, client),
            media_type="text/event-stream"
        )
    else:
        return result


@app.get("/v1/models")
async def list_models(request: Request):
    """
    OpenAI compatible models list endpoint.
    """
    if not verify_proxy_auth(request):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    return {
        "object": "list",
        "data": [
            {
                "id": settings.DEFAULT_MODEL,
                "object": "model",
                "created": 1700000000,
                "owned_by": "nvidia-nim-proxy"
            }
        ]
    }


@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """
    Anthropic compatible messages endpoint (POST /v1/messages) for Claude Code.
    """
    if not verify_proxy_auth(request):
        logger.warning("[Auth] Access denied on /v1/messages: Invalid or missing PROXY_API_KEY.")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "Invalid or missing Proxy API Key. Provide PROXY_API_KEY in x-api-key or Authorization header.",
                    "type": "authentication_error",
                    "code": 401
                }
            }
        )

    try:
        anthropic_body = await request.json()
    except Exception:
        anthropic_body = {}

    logger.info(f"[AnthropicEndpoint] Authenticated request received from Claude Code / Anthropic client")

    openai_body = anthropic_request_to_openai(anthropic_body, settings.DEFAULT_MODEL)
    is_stream = anthropic_body.get("stream", False)

    result = await send_request_with_failover(openai_body, stream=is_stream)

    if isinstance(result, JSONResponse):
        return result

    if is_stream:
        resp, client = result
        return StreamingResponse(
            stream_anthropic_response(resp, client, settings.DEFAULT_MODEL),
            media_type="text/event-stream"
        )
    else:
        anthropic_resp = openai_response_to_anthropic(result, settings.DEFAULT_MODEL)
        return anthropic_resp


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
