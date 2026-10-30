import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.errors import AppError, ProviderError
from app.llm.prompts import PROMPT_VERSION, build_messages
from app.llm.qwen import QwenGenerationAdapter
from app.llm.schemas import RequirementsSpec, SystemSpec
from app.ports import GenerationRequest
from app.services.storage import StageFiles


def settings(**overrides):
    values = {
        "qwen_base_url": "https://qwen.example/v1",
        "qwen_model": "qwen-test-model",
        "qwen_api_key": SecretStr("test-secret"),
        "qwen_api_path": "/chat/completions",
    }
    values.update(overrides)
    return Settings(**values)


def test_output_schema_maps_all_stage_families():
    assert QwenGenerationAdapter.output_schema("analyze") is RequirementsSpec
    assert QwenGenerationAdapter.output_schema("design") is SystemSpec
    assert QwenGenerationAdapter.output_schema("generate_backend") is StageFiles
    assert QwenGenerationAdapter.output_schema("repair") is StageFiles


def test_requirements_spec_checks_unique_ids_and_references():
    valid = {
        "schemaVersion": 1,
        "title": "Repair requests",
        "actors": [{"id": "dispatcher", "name": "Dispatcher"}],
        "entities": [{
            "id": "repair_request", "name": "Repair request", "fields": [
                {"id": "status", "name": "status", "type": "enum", "enumValues": ["new", "done"]}
            ]
        }],
        "rules": [{"id": "close_only_after_review", "description": "Review before close", "entityRefs": ["repair_request"]}],
        "acceptanceCriteria": [{"id": "request_can_close", "description": "A reviewed request can close", "verifies": ["repair_request", "close_only_after_review"]}],
        "assumptions": [],
    }
    assert RequirementsSpec.model_validate(valid).title == "Repair requests"
    valid["rules"].append(valid["rules"][0])
    with pytest.raises(ValidationError):
        RequirementsSpec.model_validate(valid)


def test_system_spec_checks_references():
    value = {
        "schemaVersion": 1,
        "entities": [{"id": "repair_request", "name": "Repair request", "fields": []}],
        "endpoints": [{"id": "list_repairs", "method": "GET", "path": "/api/v1/repairs", "entityRefs": ["repair_request"]}],
        "pages": [{"id": "repair_list", "name": "Repair list", "endpointRefs": ["list_repairs"]}],
        "events": [],
        "acceptanceTests": [{"id": "can_list", "description": "List repairs", "endpointRefs": ["list_repairs"], "pageRefs": ["repair_list"]}],
    }
    assert SystemSpec.model_validate(value).endpoints[0].path == "/api/v1/repairs"
    value["pages"][0]["endpointRefs"] = ["missing"]
    with pytest.raises(ValidationError):
        SystemSpec.model_validate(value)


@pytest.mark.asyncio
async def test_qwen_adapter_sends_bearer_and_normalizes_usage():
    seen = {}

    async def handler(request):
        seen["authorization"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "model": "qwen-real-id",
            "choices": [{"finish_reason": "stop", "message": {"content": '{"schemaVersion":1,"title":"Repair"}'}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = QwenGenerationAdapter(settings(), client=client)
    try:
        result = await adapter.generate(GenerationRequest("analyze", {"requirements": "repair workflow"}))
    finally:
        await client.aclose()

    assert seen["authorization"] == "Bearer test-secret"
    assert seen["body"]["model"] == "qwen-test-model"
    assert result.model_id == "qwen-real-id"
    assert result.prompt_version == PROMPT_VERSION
    assert result.input_tokens == 12 and result.output_tokens == 7
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_qwen_adapter_marks_truncation():
    async def handler(_request):
        return httpx.Response(200, json={
            "model": "qwen", "choices": [{"finish_reason": "length", "message": {"content": "{}"}}]
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = QwenGenerationAdapter(settings(), client=client)
    try:
        result = await adapter.generate(GenerationRequest("analyze", {}))
    finally:
        await client.aclose()
    assert result.finish_reason == "length"


@pytest.mark.asyncio
async def test_qwen_adapter_classifies_provider_errors_without_leaking_body():
    async def handler(_request):
        return httpx.Response(503, text="secret upstream diagnostic")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = QwenGenerationAdapter(settings(), client=client)
    try:
        with pytest.raises(ProviderError) as error:
            await adapter.generate(GenerationRequest("analyze", {}))
    finally:
        await client.aclose()
    assert error.value.transient is True
    assert "secret upstream" not in str(error.value)


def test_missing_credentials_fail_closed():
    with pytest.raises(AppError) as error:
        QwenGenerationAdapter(Settings())
    assert error.value.error.code == "qwen_not_configured"


def test_prompt_uses_json_and_stage_contract():
    messages = build_messages(GenerationRequest("generate_backend", {"systemSpec": {}}))
    assert "C# 14" in messages[0]["content"]
    assert "FastAPI" in messages[0]["content"]
    assert messages[1]["content"].startswith('{"stage":"generate_backend"')
