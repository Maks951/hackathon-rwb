"""OpenAI-compatible HTTP transport for the configured Qwen provider."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.errors import AppError, ProviderError
from app.llm.prompts import PROMPT_VERSION, build_messages
from app.llm.schemas import RequirementsSpec, SystemSpec
from app.ports import GenerationRequest, GenerationResponse, GenerationStage
from app.services.storage import StageFiles


def normalize_json_content(content: str) -> str:
    """Remove provider reasoning/fences; never repair or search inside invalid JSON."""
    text = content.strip()
    try:
        json.loads(text)
        return text  # Preserve literal </think> tags inside valid JSON strings/files.
    except json.JSONDecodeError:
        pass
    if "</think>" in text:
        prefix, _, suffix = text.partition("</think>")
        if prefix.lstrip().startswith("<think>") or not prefix.lstrip().startswith(
            ("{", "[", "```")
        ):
            text = suffix.strip()
    lines = text.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        text = "\n".join(lines[1:-1]).strip()
    return text


class QwenGenerationAdapter:
    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None):
        if not settings.qwen_base_url or not settings.qwen_model or not settings.qwen_api_key:
            raise AppError(
                "qwen_not_configured",
                "Qwen не настроен: задайте QWEN_BASE_URL, QWEN_MODEL и QWEN_API_KEY.",
                503,
            )
        parsed = urlsplit(settings.qwen_base_url)
        allowed_http_hosts = {"localhost", "127.0.0.1"}
        if settings.qwen_allow_docker_host_http:
            allowed_http_hosts.add("host.docker.internal")
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http"
                and parsed.hostname not in allowed_http_hosts
                and not (
                    settings.qwen_allow_vm_http
                    and parsed.hostname == "10.10.10.10"
                    and parsed.port == 4000
                    and parsed.path.rstrip("/") == "/v1"
                )
            )
        ):
            raise AppError(
                "invalid_qwen_url", "QWEN_BASE_URL должен быть безопасным HTTP(S) URL.", 503
            )
        if (
            not settings.qwen_api_path.startswith("/")
            or ".." in settings.qwen_api_path
            or "?" in settings.qwen_api_path
            or "#" in settings.qwen_api_path
            or settings.qwen_api_path.startswith("//")
            or (
                parsed.path.rstrip("/").endswith("/v1")
                and settings.qwen_api_path.startswith("/v1/")
            )
        ):
            raise AppError("invalid_qwen_url", "Недопустимый QWEN_API_PATH.", 503)
        self.base_url = settings.qwen_base_url.rstrip("/")
        self.api_path = settings.qwen_api_path
        self.model = settings.qwen_model
        self.api_key = settings.qwen_api_key.get_secret_value()
        self.timeout = settings.llm_timeout_seconds
        self.max_response_bytes = settings.max_response_bytes
        self.enable_thinking = settings.qwen_enable_thinking
        self.client = client

    @staticmethod
    def output_schema(stage: GenerationStage) -> type[BaseModel]:
        if stage == "analyze":
            return RequirementsSpec
        if stage == "design":
            return SystemSpec
        return StageFiles

    async def generate(self, request: GenerationRequest) -> GenerationResponse:
        payload = {
            "model": self.model,
            "messages": build_messages(request),
            "temperature": 0.7,
            "top_p": 0.8,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": self.enable_thinking},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        url = self.base_url + self.api_path
        try:
            if self.client is not None:
                response = await self.client.post(
                    url, json=payload, headers=headers, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(url, json=payload, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError):
            raise ProviderError(transient=True) from None

        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderError(transient=True)
        if response.status_code >= 400:
            raise ProviderError(transient=False)
        if len(response.content) > self.max_response_bytes:
            raise AppError("output_too_large", "Ответ Qwen превышает лимит размера.", 413)
        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            finish_reason = choice.get("finish_reason") or "unknown"
            content = message.get("content")
            # Some servers separate reasoning and leave final content empty when the
            # token budget is exhausted. Preserve length so the worker diagnoses it.
            if finish_reason == "length" and content is None:
                content = ""
            if isinstance(content, list):
                content = "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            if not isinstance(content, str) or (not content.strip() and finish_reason != "length"):
                raise ValueError("empty content")
            usage = body.get("usage") or {}
            input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
            output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
            if finish_reason == "length":
                normalized_finish = "length"
            elif finish_reason in {"stop", "end_turn", "completed"}:
                normalized_finish = "stop"
            else:
                normalized_finish = str(finish_reason)
            return GenerationResponse(
                content=normalize_json_content(content),
                model_id=str(body.get("model") or self.model),
                prompt_version=PROMPT_VERSION,
                finish_reason=normalized_finish,
                input_tokens=input_tokens if isinstance(input_tokens, int) else None,
                output_tokens=output_tokens if isinstance(output_tokens, int) else None,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            raise ProviderError(transient=False) from None
