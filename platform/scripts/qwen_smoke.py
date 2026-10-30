"""Make one real, minimal Qwen analyze call using the configured provider credentials."""
import asyncio

from app.config import Settings
from app.llm.qwen import QwenGenerationAdapter
from app.ports import GenerationRequest


async def main() -> None:
    settings = Settings()
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
    parsed = adapter.output_schema("analyze").model_validate_json(response.content)
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
