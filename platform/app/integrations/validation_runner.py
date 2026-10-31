import base64
from dataclasses import asdict
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from app.errors import AppError
from app.ports import CheckResult, ValidationReport
from app.runner.protocol import CHECKS, digest_manifest
from app.services.storage import Storage


class RunnerCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    passed: StrictBool
    message: str = Field(max_length=8192)


class RunnerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspaceId: str
    manifestSha256: str
    checks: list[RunnerCheck] = Field(min_length=6, max_length=6)


class HttpValidationRunner:
    def __init__(self, settings, *, client=None):
        parsed = urlsplit(settings.runner_url or "")
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or (
                parsed.scheme == "http"
                and parsed.hostname
                not in {"runner", "localhost", "127.0.0.1", "host.docker.internal"}
            )
        ):
            raise ValueError("Invalid runner URL")
        if not settings.runner_token:
            raise ValueError("RWB_RUNNER_TOKEN is required")
        self.settings = settings
        self.client = client

    async def validate(self, workspace):
        files = Storage(self.settings).workspace_files(workspace)
        manifest = [asdict(a) for a in workspace.files]
        digest = digest_manifest(manifest)
        payload = dict(
            workspaceId=workspace.id,
            manifest=manifest,
            manifestSha256=digest,
            files={n: base64.b64encode(b).decode() for n, b in files.items()},
        )

        async def send(client):
            async with client.stream(
                "POST",
                self.settings.runner_url.rstrip("/") + "/validate",
                json=payload,
                headers={
                    "Authorization": "Bearer " + self.settings.runner_token.get_secret_value()
                },
                timeout=self.settings.runner_timeout_seconds + 30,
            ) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > 65536:
                        raise ValueError("Runner response too large")
                return RunnerResponse.model_validate_json(content)

        try:
            if self.client is not None:
                report = await send(self.client)
            else:
                async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
                    report = await send(client)
            if (
                report.workspaceId != workspace.id
                or report.manifestSha256 != digest
                or sorted(c.name for c in report.checks) != sorted(CHECKS)
            ):
                raise ValueError("Report does not match workspace/checks")
        except (httpx.HTTPError, ValueError):
            raise AppError(
                "runner_unavailable", "Runner недоступен или вернул неверный отчёт.", 503
            ) from None
        return ValidationReport(
            tuple(CheckResult(c.name, c.passed, c.message) for c in report.checks)
        )
