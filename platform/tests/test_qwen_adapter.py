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
        "entities": [
            {
                "id": "repair_request",
                "name": "Repair request",
                "fields": [
                    {
                        "id": "status",
                        "name": "status",
                        "type": "enum",
                        "enumValues": ["new", "done"],
                    }
                ],
            }
        ],
        "rules": [
            {
                "id": "close_only_after_review",
                "description": "Review before close",
                "entityRefs": ["repair_request"],
            }
        ],
        "acceptanceCriteria": [
            {
                "id": "request_can_close",
                "description": "A reviewed request can close",
                "verifies": ["repair_request", "close_only_after_review"],
            }
        ],
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
        "endpoints": [
            {
                "id": "list_repairs",
                "method": "GET",
                "path": "/api/v1/repairs",
                "entityRefs": ["repair_request"],
            }
        ],
        "pages": [{"id": "repair_list", "name": "Repair list", "endpointRefs": ["list_repairs"]}],
        "events": [],
        "acceptanceTests": [
            {
                "id": "can_list",
                "description": "List repairs",
                "endpointRefs": ["list_repairs"],
                "pageRefs": ["repair_list"],
            }
        ],
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
        return httpx.Response(
            200,
            json={
                "model": "qwen-real-id",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"schemaVersion":1,"title":"Repair"}'},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 7},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = QwenGenerationAdapter(settings(), client=client)
    try:
        result = await adapter.generate(
            GenerationRequest("analyze", {"requirements": "repair workflow"})
        )
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
        return httpx.Response(
            200,
            json={
                "model": "qwen",
                "choices": [{"finish_reason": "length", "message": {"content": "{}"}}],
            },
        )

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


@pytest.mark.parametrize("host", ["host.docker.internal", "10.10.10.10", "qwen.example"])
def test_non_loopback_http_requires_specific_docker_opt_in(host):
    with pytest.raises(AppError):
        QwenGenerationAdapter(settings(qwen_base_url=f"http://{host}:4000/v1"))


def test_explicit_docker_host_http_is_accepted():
    adapter = QwenGenerationAdapter(
        settings(
            qwen_base_url="http://host.docker.internal:4000/v1",
            qwen_allow_docker_host_http=True,
        )
    )
    assert adapter.base_url == "http://host.docker.internal:4000/v1"


@pytest.mark.parametrize("host", ["10.10.10.10", "qwen.example", "host.docker.internal.example"])
def test_docker_opt_in_does_not_allow_other_http_hosts(host):
    with pytest.raises(AppError):
        QwenGenerationAdapter(
            settings(
                qwen_base_url=f"http://{host}:4000/v1",
                qwen_allow_docker_host_http=True,
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wrapper",
    [
        "{json}",
        "<think>Reasoning about the schema.</think>\n{json}",
        "Reasoning without an opening tag.\n</think>\n{json}",
        "```json\n{json}\n```",
        "```\n{json}\n```",
        "<think>Reasoning.</think>\n```json\n{json}\n```",
    ],
)
async def test_provider_wrappers_are_removed_before_strict_validation(wrapper):
    document = json.dumps({"schemaVersion": 1, "title": "Repair requests"})

    async def handler(_request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": wrapper.replace("{json}", document)},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = QwenGenerationAdapter(settings(), client=client)
        result = await adapter.generate(
            GenerationRequest("analyze", {"requirements": "Repair requests"})
        )
    assert RequirementsSpec.model_validate_json(result.content).title == "Repair requests"


def test_json_cleanup_preserves_tags_inside_generated_file_content():
    from app.llm.qwen import normalize_json_content

    text = json.dumps({"schemaVersion": 1, "title": "Keep </think> and ``` in a string"})
    assert normalize_json_content(text) == text
    assert normalize_json_content("```json\n" + text + "\n```") == text


@pytest.mark.parametrize(
    "content",
    [
        '<think>Reasoning.</think>\n{"schemaVersion":1,"title":',
        '<think>Reasoning.</think>\n{"schemaVersion":1,"title":"x","unexpected":true}',
        '<think>Reasoning.</think>\n{"schemaVersion":1,"title":"x"} trailing prose',
        '{"schemaVersion":1,"title":"x"} {"title":"y"}',
        'Here is your answer: {"schemaVersion":1,"title":"x"}',
    ],
)
def test_cleanup_does_not_hide_malformed_json_or_schema_errors(content):
    from app.llm.qwen import normalize_json_content

    with pytest.raises(ValidationError):
        RequirementsSpec.model_validate_json(normalize_json_content(content))


@pytest.mark.parametrize("stage,schema", [("analyze", RequirementsSpec), ("design", SystemSpec)])
def test_structured_stage_prompts_embed_the_actual_schema_and_enum_rules(stage, schema):
    system = build_messages(GenerationRequest(stage, {}))[0]["content"]
    marker = "Return an instance conforming to it, not the schema itself:\n"
    assert json.loads(system.split(marker, 1)[1]) == schema.model_json_schema()
    assert "enumValues must always be an array of strings, never null" in system
    assert "use enumValues: [] or omit it" in system


@pytest.mark.parametrize(
    "field_type,enum_values",
    [
        ("string", None),
        ("string", ""),
        ("string", {}),
        ("enum", None),
        ("enum", []),
        ("enum", ["new", 1]),
        ("string", ["unexpected"]),
    ],
)
def test_enum_contract_remains_strict(field_type, enum_values):
    from app.llm.schemas import FieldSpec

    with pytest.raises(ValidationError):
        FieldSpec.model_validate(
            {
                "id": "status",
                "name": "Status",
                "type": field_type,
                "enumValues": enum_values,
            }
        )
