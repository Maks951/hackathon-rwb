"""Make one real, minimal Qwen analyze call using the configured provider credentials."""
import argparse
import asyncio
import getpass

from pydantic import ValidationError

from app.config import Settings
from app.llm.qwen import QwenGenerationAdapter
from app.ports import GenerationRequest


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--prompt-key", action="store_true")
    parser.add_argument("--allow-docker-host-http", action="store_true")
    args = parser.parse_args()
    overrides = {}
    if args.base_url:
        overrides["qwen_base_url"] = args.base_url
    if args.model:
        overrides["qwen_model"] = args.model
    if args.prompt_key:
        key = getpass.getpass("Qwen API key (hidden): ").strip()
        if not key:
            raise SystemExit("API key is empty; no request sent.")
        overrides["qwen_api_key"] = key
    if args.allow_docker_host_http:
        overrides["qwen_allow_docker_host_http"] = True
    settings = Settings(**overrides)
    adapter = QwenGenerationAdapter(settings)
    response = await adapter.generate(
        GenerationRequest(
            stage="analyze",
            inputs={
                "requirements": (
                    "Create a small repair-request tracker. Users can submit a request; "
                    "a dispatcher assigns it; status changes are recorded."
                )
            },
        )
    )
    try:
        parsed = adapter.output_schema("analyze").model_validate_json(response.content)
    except ValidationError as error:
        print({
            "ok": False,
            "modelId": response.model_id,
            "finishReason": response.finish_reason,
            "containsThinkTag": "</think>" in response.content,
            "validationErrors": error.errors(include_input=False, include_url=False),
        })
        raise SystemExit(1) from None
    print(
        {
            "ok": True,
            "modelId": response.model_id,
            "promptVersion": response.prompt_version,
            "finishReason": response.finish_reason,
            "inputTokens": response.input_tokens,
            "outputTokens": response.output_tokens,
            "requirementsTitle": parsed.title,
            "entityCount": len(parsed.entities),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
