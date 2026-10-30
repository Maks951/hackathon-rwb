from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="RWB_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    runtime_factory: str | None = None
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DATABASE_URL", "RWB_DATABASE_URL"),
        repr=False,
    )
    generated_root: Path = Path("../generated")
    templates_root: Path = Path("../templates")
    cors_origins: list[str] = Field(default_factory=list)
    run_timeout_seconds: float = Field(default=900, gt=0)
    llm_timeout_seconds: float = Field(default=120, gt=0)
    heartbeat_seconds: float = Field(default=10, gt=0)
    stale_seconds: float = Field(default=60, gt=0)
    poll_seconds: float = Field(default=2, gt=0)
    max_files: int = Field(default=500, gt=0)
    max_file_bytes: int = Field(default=1_048_576, gt=0)
    max_tree_bytes: int = Field(default=25_165_824, gt=0)
    max_response_bytes: int = Field(default=8_388_608, gt=0)
    max_events: int = Field(default=200, ge=1, le=1000)
    database_connect_timeout_seconds: int = Field(default=3, ge=1, le=30)

    @model_validator(mode="after")
    def check_heartbeat(self) -> "Settings":
        if self.stale_seconds < self.heartbeat_seconds * 3:
            raise ValueError("stale_seconds must be at least 3 * heartbeat_seconds")
        return self
