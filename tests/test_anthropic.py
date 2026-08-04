from app.anthropic_translator import (
    anthropic_request_to_openai,
    openai_response_to_anthropic
)


def test_anthropic_request_conversion():
    anthropic_req = {
        "model": "claude-3-5-sonnet-20241022",
        "system": "You are a helpful assistant.",
        "messages": [
            {"role": "user", "content": "Hello!"}
        ],
        "max_tokens": 100,
        "temperature": 0.5
    }

    openai_req = anthropic_request_to_openai(anthropic_req, "z-ai/glm-5.2")

    assert openai_req["model"] == "z-ai/glm-5.2"
    assert len(openai_req["messages"]) == 2
    assert openai_req["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
    assert openai_req["messages"][1] == {"role": "user", "content": "Hello!"}
    assert openai_req["max_tokens"] == 100
    assert openai_req["temperature"] == 0.5


def test_openai_response_conversion():
    openai_resp = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "model": "z-ai/glm-5.2",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Test response"
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20
        }
    }

    anthropic_resp = openai_response_to_anthropic(openai_resp, "z-ai/glm-5.2")

    assert anthropic_resp["type"] == "message"
    assert anthropic_resp["role"] == "assistant"
    assert anthropic_resp["model"] == "z-ai/glm-5.2"
    assert anthropic_resp["content"][0]["type"] == "text"
    assert anthropic_resp["content"][0]["text"] == "Test response"
    assert anthropic_resp["usage"]["input_tokens"] == 10
    assert anthropic_resp["usage"]["output_tokens"] == 20
    assert anthropic_resp["stop_reason"] == "end_turn"
