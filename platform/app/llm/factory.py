"""Small factory for Yaroslav's Runtime composition root."""
from app.config import Settings
from app.llm.qwen import QwenGenerationAdapter


def create_qwen_adapter(settings: Settings) -> QwenGenerationAdapter:
    return QwenGenerationAdapter(settings)
