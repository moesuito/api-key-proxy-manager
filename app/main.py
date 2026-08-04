import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.key_manager import key_manager, verify_keys_on_startup
from app.logger import logger
from app.anthropic_translator import anthropic_request_to_openai, openai_response_to_anthropic
from app.nim_client import send_request_with_failover, stream_openai_response, stream_anthropic_response


def verify_proxy_auth(request: Request) -> bool:
    """
    Verifica se a requisição enviou a PROXY_API_KEY correta.
    Aceita no header 'Authorization: Bearer <KEY>' ou 'x-api-key: <KEY>'.
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    keys = settings.NVIDIA_API_KEYS
    key_manager.set_keys(keys)
    host_url = f"http://localhost:{settings.PORT}"
    
    logger.info("=" * 65)
    logger.info(f" NVIDIA NIM API PROXY INICIADO SUCESSO")
    logger.info(f" PROXY_API_KEY FIXA : {settings.PROXY_API_KEY}")
    logger.info(f" MODELO PADRÃO     : {settings.DEFAULT_MODEL}")
    logger.info(f" ENDPOINT OPENAI   : {host_url}/v1")
    logger.info(f" ENDPOINT ANTHROPIC: {host_url}")
    logger.info("-----------------------------------------------------------------")
    # Testa e valida todas as chaves cadastradas na inicialização
    await verify_keys_on_startup(settings.NVIDIA_BASE_URL)
    logger.info("=" * 65)
    yield


app = FastAPI(
    title="NVIDIA NIM API Key Proxy",
    description="Proxy OpenAI & Anthropic Compatible com Autenticação e Rotação Automática de Keys",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/api/hello", methods=["GET", "HEAD"])
async def api_hello():
    """Endpoint de ping/healthcheck consultado pelo Claude Code na inicialização."""
    return {"status": "ok", "service": "nvidia-nim-proxy"}


@app.get("/health")
async def health_check():
    """Endpoint de status e métricas de uso das API Keys."""
    status = key_manager.get_status()
    return {
        "status": "online",
        "default_model": settings.DEFAULT_MODEL,
        "proxy_api_key_configured": bool(settings.PROXY_API_KEY),
        "key_manager": status
    }


@app.get("/v1/models")
async def list_models():
    """Endpoint no padrão OpenAI para listar os modelos disponíveis."""
    return {
        "object": "list",
        "data": [
            {
                "id": settings.DEFAULT_MODEL,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "nvidia"
            }
        ]
    }


@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    Endpoint compatível com OpenAI (POST /v1/chat/completions).
    """
    if not verify_proxy_auth(request):
        logger.warning("[Auth] Acesso negado em /v1/chat/completions: PROXY_API_KEY incorreta ou ausente.")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "API Key do Proxy incorreta ou ausente. Forneça a PROXY_API_KEY no header Authorization.",
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


@app.post("/v1/messages")
async def anthropic_messages(request: Request):
    """
    Endpoint compatível com Anthropic (POST /v1/messages) para uso no Claude Code.
    """
    if not verify_proxy_auth(request):
        logger.warning("[Auth] Acesso negado em /v1/messages: PROXY_API_KEY incorreta ou ausente.")
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "message": "API Key do Proxy incorreta ou ausente. Forneça a PROXY_API_KEY no header x-api-key ou Authorization.",
                    "type": "authentication_error",
                    "code": 401
                }
            }
        )

    try:
        anthropic_body = await request.json()
    except Exception:
        anthropic_body = {}

    logger.info(f"[AnthropicEndpoint] Recebida requisição autenticada do Claude Code / cliente Anthropic")

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
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=True)
