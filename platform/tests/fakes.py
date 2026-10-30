"""Test doubles only. These are not production adapters and never run from the app."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.errors import AppError
from app.ports import (
    CheckResult,
    GenerationResponse,
    RunRecord,
    RunStatus,
    ValidationReport,
)
from app.schemas.runs import EventDto, StepDto, StepStatus
from app.services.storage import StageFiles

CHECKS = ("backend_build", "backend_tests", "admin_build", "pwa_build", "api_contract", "security")
BACKEND_FILE = "backend/src/Generated.Api/Generated/Module.cs"


class MemoryRepository:
    def __init__(self):
        self.project_id = uuid4()
        self.requirements = "Manage service tickets and their statuses."
        self.runs = {}
        self.keys = {}
        self.steps = {}
        self.events = {}
        self.calls = []
        self.packages = {}
        self.outputs = {}
        self.heartbeats = 0
        self.stale_args = None
        self.heartbeat_ok = True

    async def ping(self):
        return True

    async def create_run(self, project_id, idempotency_key):
        if idempotency_key in self.keys:
            run = self.runs[self.keys[idempotency_key]]
            if run.project_id != project_id:
                raise AppError("idempotency_conflict", "Ключ уже использован.", 409)
            return run
        if project_id != self.project_id:
            raise AppError("not_found", "Проект не найден.", 404)
        if any(r.status in (RunStatus.QUEUED, RunStatus.RUNNING) for r in self.runs.values()):
            raise AppError("active_run", "Запуск уже выполняется.", 409)
        run = RunRecord(uuid4(), project_id, self.requirements, RunStatus.QUEUED, datetime.now(UTC))
        self.runs[run.id] = run
        self.keys[idempotency_key] = run.id
        return run

    async def get_run(self, run_id):
        return self.runs.get(run_id)

    async def list_steps(self, run_id):
        return [step for owner, step in self.steps.values() if owner == run_id]

    async def list_events(self, run_id, after, limit):
        return [e for e in self.events.get(run_id, []) if e.sequence > after][:limit]

    async def get_package(self, run_id):
        return self.packages.get(run_id)

    async def claim_next(self):
        for run in self.runs.values():
            if run.status == RunStatus.QUEUED:
                claimed = replace(run, status=RunStatus.RUNNING)
                self.runs[run.id] = claimed
                return claimed
        return None

    async def heartbeat(self, run_id, now):
        self.heartbeats += 1
        return self.heartbeat_ok

    async def fail_stale(self, before, now):
        self.stale_args = (before, now)
        return 0

    async def start_step(self, run_id, key, attempt, input_path, now):
        step = StepDto(id=uuid4(), key=key, attempt=attempt, status=StepStatus.RUNNING, error=None)
        self.steps[step.id] = (run_id, step)
        self.runs[run_id] = replace(self.runs[run_id], current_step=key)
        return step

    async def complete_step(self, step_id, output_path, metadata, artifacts, now, error=None):
        owner, step = self.steps[step_id]
        status = StepStatus.FAILED if error else StepStatus.SUCCEEDED
        self.steps[step_id] = (owner, step.model_copy(update={"status": status, "error": error}))
        self.outputs[step_id] = (output_path, metadata, artifacts)

    async def record_call(self, run_id, key, attempt, metadata, artifact):
        self.calls.append((run_id, key, attempt, metadata, artifact))

    async def fail_step(self, step_id, error, now):
        owner, step = self.steps[step_id]
        self.steps[step_id] = (
            owner,
            step.model_copy(update={"status": StepStatus.FAILED, "error": error}),
        )

    async def add_event(self, run_id, type, message):
        events = self.events.setdefault(run_id, [])
        events.append(
            EventDto(
                id=uuid4(),
                sequence=len(events) + 1,
                type=type,
                message=message,
                created_at=datetime.now(UTC),
            )
        )

    async def set_validation(self, run_id, status):
        self.runs[run_id] = replace(self.runs[run_id], validation_status=status)

    async def set_deployment(self, run_id, status, preview_url):
        self.runs[run_id] = replace(
            self.runs[run_id], deployment_status=status, preview_url=preview_url
        )

    async def set_repository_url(self, run_id, url):
        self.runs[run_id] = replace(self.runs[run_id], repository_url=url)

    async def save_package(self, run_id, artifact):
        self.packages[run_id] = artifact

    async def finish_run(self, run_id, status, error, now):
        self.runs[run_id] = replace(
            self.runs[run_id], status=status, error=error, finished_at=now, current_step=None
        )


class RequirementsFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schemaVersion: Literal[1]
    title: str


class SystemFixture(BaseModel):
    schemaVersion: Literal[1]
    endpoints: list[dict[str, str]]


class ScriptedGeneration:
    def __init__(self, domain="tickets"):
        self.requests = []
        self.domain = domain
        self.repairs = 0
        self.analyze_responses = []

    def output_schema(self, stage):
        return {"analyze": RequirementsFixture, "design": SystemFixture}.get(stage, StageFiles)

    async def generate(self, request):
        self.requests.append(request)
        if request.stage == "analyze" and self.analyze_responses:
            value = self.analyze_responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        if request.stage == "analyze":
            content = {"schemaVersion": 1, "title": self.domain}
        elif request.stage == "design":
            content = {
                "schemaVersion": 1,
                "endpoints": [
                    {"id": "list", "method": "GET", "path": f"/api/v1/{self.domain}"},
                ],
            }
        else:
            name = {
                "generate_db": "database/generated/schema.sql",
                "generate_backend": BACKEND_FILE,
                "generate_web": "admin/src/app/generated/page.ts",
                "generate_pwa": "pwa/src/app/generated/page.ts",
                "generate_tests_docs": "docs/system-analysis.md",
                "repair": BACKEND_FILE,
            }[request.stage]
            if request.stage == "repair":
                self.repairs += 1
            content = {
                "schemaVersion": 1,
                "files": [
                    {"path": name, "content": f"test fixture {self.domain}, repair={self.repairs}"},
                ],
                "notes": [],
            }
        return GenerationResponse(
            json.dumps(content), "test-only-model", "fixture-v1", "stop", 10, 20
        )


class ScriptedValidator:
    def __init__(self, failures=0):
        self.failures = failures
        self.workspaces = []

    async def validate(self, workspace):
        self.workspaces.append(workspace)
        passed = len(self.workspaces) > self.failures
        return ValidationReport(
            tuple(CheckResult(name, passed, "fixture result") for name in CHECKS)
        )


async def queued_run(repo):
    return await repo.create_run(repo.project_id, uuid4())
