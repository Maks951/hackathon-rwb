import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.llm.qwen import QwenGenerationAdapter
from app.ports import GenerationRequest


@pytest.mark.parametrize("enabled", [False, True])
async def test_thinking_control_is_sent_to_server(enabled):
    seen = {}

    async def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"schemaVersion":1,"files":[],"notes":[]}'},
                    }
                ]
            },
        )

    settings = Settings(
        qwen_base_url="https://qwen.example/v1",
        qwen_model="qwen-test",
        qwen_api_key=SecretStr("test-only"),
        qwen_enable_thinking=enabled,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = QwenGenerationAdapter(settings, client=client)
        await adapter.generate(GenerationRequest("generate_backend", {}))
    assert seen["chat_template_kwargs"] == {"enable_thinking": enabled}
    assert "extra_body" not in seen


def test_thinking_is_disabled_by_default():
    assert Settings(_env_file=None).qwen_enable_thinking is False


async def test_reasoning_only_truncation_preserves_length_diagnostic():
    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": None,
                            "reasoning_content": "long reasoning",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 4621, "completion_tokens": 28147},
            },
        )

    settings = Settings(
        qwen_base_url="https://qwen.example/v1",
        qwen_model="qwen-test",
        qwen_api_key=SecretStr("test-only"),
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await QwenGenerationAdapter(settings, client=client).generate(
            GenerationRequest("generate_backend", {})
        )
    assert response.finish_reason == "length"
    assert response.output_tokens == 28147
    assert response.content == ""
