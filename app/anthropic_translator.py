import json
import uuid
from typing import Dict, Any, List, Generator


def anthropic_request_to_openai(anthropic_body: Dict[str, Any], default_model: str) -> Dict[str, Any]:
    """
    Converte uma requisição no formato Anthropic (/v1/messages) para o formato OpenAI (/v1/chat/completions).
    """
    openai_messages = []

    # 1. Trata o System Prompt
    system_field = anthropic_body.get("system")
    if system_field:
        if isinstance(system_field, str):
            openai_messages.append({"role": "system", "content": system_field})
        elif isinstance(system_field, list):
            system_texts = []
            for block in system_field:
                if isinstance(block, dict) and block.get("type") == "text":
                    system_texts.append(block.get("text", ""))
                elif isinstance(block, str):
                    system_texts.append(block)
            if system_texts:
                openai_messages.append({"role": "system", "content": "\n".join(system_texts)})

    # 2. Converte as mensagens
    raw_messages = anthropic_body.get("messages", [])
    for msg in raw_messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            text_parts = []
            tool_calls = []
            tool_results = []

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")

                if block_type == "text":
                    text_parts.append(block.get("text", ""))
                elif block_type == "tool_use":
                    # Chamada de ferramenta feita pelo modelo
                    tool_calls.append({
                        "id": block.get("id", f"toolu_{uuid.uuid4().hex[:8]}"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {}))
                        }
                    })
                elif block_type == "tool_result":
                    # Resultado da ferramenta retornado pelo usuário
                    tr_content = block.get("content", "")
                    if isinstance(tr_content, list):
                        tr_content_str = "\n".join(
                            b.get("text", "") for b in tr_content if isinstance(b, dict) and b.get("type") == "text"
                        )
                    else:
                        tr_content_str = str(tr_content)

                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id"),
                        "content": tr_content_str
                    })

            if role == "assistant" and tool_calls:
                msg_obj = {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                    "tool_calls": tool_calls
                }
                openai_messages.append(msg_obj)
            elif text_parts:
                openai_messages.append({"role": role, "content": "\n".join(text_parts)})

            # Se existiam tool_results, insere como mensagens de role="tool"
            for tr in tool_results:
                openai_messages.append(tr)

    # 3. Converte as ferramentas (tools)
    openai_tools = None
    if "tools" in anthropic_body and isinstance(anthropic_body["tools"], list):
        openai_tools = []
        for t in anthropic_body["tools"]:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t.get("name"),
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}})
                }
            })

    # 4. Monta o payload final para a OpenAI / NVIDIA NIM
    openai_body = {
        "model": default_model,  # Força o modelo padrão fixo (ex: z-ai/glm-5.2)
        "messages": openai_messages,
        "stream": anthropic_body.get("stream", False)
    }

    if "max_tokens" in anthropic_body:
        openai_body["max_tokens"] = anthropic_body["max_tokens"]
    if "temperature" in anthropic_body:
        openai_body["temperature"] = anthropic_body["temperature"]
    if "top_p" in anthropic_body:
        openai_body["top_p"] = anthropic_body["top_p"]
    if openai_tools:
        openai_body["tools"] = openai_tools

    return openai_body


def openai_response_to_anthropic(openai_resp: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Converte uma resposta não-stream no formato OpenAI para o formato Anthropic.
    """
    msg_id = f"msg_{uuid.uuid4().hex[:12]}"
    choices = openai_resp.get("choices", [])

    content_blocks = []
    stop_reason = "end_turn"

    if choices:
        choice = choices[0]
        message = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "stop")

        if finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "length":
            stop_reason = "max_tokens"

        # Texto
        text_content = message.get("content")
        if text_content:
            content_blocks.append({"type": "text", "text": text_content})

        # Tool calls
        tool_calls = message.get("tool_calls", [])
        for tc in tool_calls:
            func = tc.get("function", {})
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except Exception:
                args = {}

            content_blocks.append({
                "type": "tool_use",
                "id": tc.get("id", f"toolu_{uuid.uuid4().hex[:8]}"),
                "name": func.get("name"),
                "input": args
            })

    if not content_blocks:
        content_blocks.append({"type": "text", "text": ""})

    usage = openai_resp.get("usage", {})

    return {
        "id": msg_id,
        "type": "message",
        "role": "assistant",
        "model": model_name,
        "content": content_blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0)
        }
    }


def format_sse(event_type: str, data_obj: Dict[str, Any]) -> str:
    """Formata evento SSE de acordo com a especificação da Anthropic."""
    return f"event: {event_type}\ndata: {json.dumps(data_obj)}\n\n"
