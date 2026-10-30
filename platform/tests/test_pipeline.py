import asyncio
import json
from dataclasses import replace

import pytest

from app.errors import AppError, ProviderError
from app.ports import CheckResult, GenerationResponse, ValidationReport
from app.schemas.runs import DeploymentStatus, RunStatus, StepStatus, ValidationStatus
from app.services.storage import Storage
from app.worker import Worker
from tests.fakes import BACKEND_FILE, ScriptedGeneration, queued_run


@pytest.mark.parametrize("domain", ["parking", "tickets"])
async def test_full_orchestration_uses_one_persisted_contract_and_packages(
    settings, runtime, domain
):
    runtime.generation = ScriptedGeneration(domain)
    repo = runtime.repository
    queued = await queued_run(repo)
    repo.requirements = "Changed live requirements must not alter the existing run."
    assert await Worker(runtime, settings).run_once()
    run = await repo.get_run(queued.id)
    assert run.status == RunStatus.SUCCEEDED
    assert run.validation_status == ValidationStatus.PASSED
    assert run.deployment_status == DeploymentStatus.SKIPPED
    assert run.repository_url is None and run.preview_url is None
    assert run.finished_at is not None
    assert repo.packages[run.id].size_bytes > 0
    requests = runtime.generation.requests
    assert requests[0].inputs["requirements"] == queued.requirements_snapshot
    code_requests = [r for r in requests if r.stage.startswith("generate_")]
    assert len({json.dumps(r.inputs["generatedApi"], sort_keys=True) for r in code_requests}) == 1
    assert code_requests[0].inputs["generatedApi"]["endpoints"][0]["path"] == f"/api/v1/{domain}"
    storage = Storage(settings)
    assert all(storage.verified_path(call[-1]).is_file() for call in repo.calls)
    assert all(step.status == StepStatus.SUCCEEDED for step in await repo.list_steps(run.id))
    assert repo.stale_args is not None
    assert not await Worker(runtime, settings).run_once()


async def test_repair_uses_new_trees_revalidates_and_preserves_old_failures(settings, runtime):
    runtime.validator.failures = 1
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.SUCCEEDED
    assert runtime.generation.repairs == 1
    old, new = runtime.validator.workspaces
    assert old.id != new.id
    storage = Storage(settings)
    assert b"repair=0" in storage.workspace_files(old)[BACKEND_FILE]
    assert b"repair=1" in storage.workspace_files(new)[BACKEND_FILE]
    checks = [
        step for step in await runtime.repository.list_steps(run.id) if step.key == "validate"
    ]
    assert [step.status for step in checks] == [StepStatus.FAILED, StepStatus.SUCCEEDED]
    assert [step.attempt for step in checks] == [1, 2]


async def test_validation_failure_is_terminal_after_two_repairs_without_package_or_deploy(
    settings, runtime
):
    runtime.validator.failures = 100
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.FAILED
    assert run.error.code == "validation_failed"
    assert run.validation_status == ValidationStatus.FAILED
    assert runtime.generation.repairs == 2
    assert len(runtime.validator.workspaces) == 3
    assert not runtime.repository.packages
    assert run.deployment_status != DeploymentStatus.DEPLOYED


async def test_empty_report_cannot_pass_validation(settings, runtime):
    async def validate(workspace):
        return ValidationReport(())

    runtime.validator.validate = validate
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    assert (await runtime.repository.get_run(queued.id)).status == RunStatus.FAILED
    assert not runtime.repository.packages


def test_runner_status_is_a_boolean_not_a_truthy_string():
    names = (
        "backend_build",
        "backend_tests",
        "admin_build",
        "pwa_build",
        "api_contract",
        "security",
        "documentation",
    )
    checks = tuple(CheckResult(name, True, "completed") for name in names)
    assert ValidationReport(checks).passed
    invalid = (CheckResult("backend_build", "false", "invalid adapter payload"), *checks[1:])
    assert not ValidationReport(invalid).passed


async def test_bad_json_has_one_correction_and_preserves_metadata(settings, runtime):
    runtime.generation.analyze_responses = [
        GenerationResponse(
            '{"title": "SECRET", "schemaVersion": "bad"}',
            "test-model",
            "v1",
        )
    ]
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    assert (await runtime.repository.get_run(queued.id)).status == RunStatus.SUCCEEDED
    assert len([r for r in runtime.generation.requests if r.stage == "analyze"]) == 2
    correction = runtime.generation.requests[1]
    assert correction.json_errors and "SECRET" not in str(correction.json_errors)
    assert len([call for call in runtime.repository.calls if call[1] == "analyze"]) == 2


async def test_invalid_json_stops_after_one_correction(settings, runtime):
    runtime.generation.analyze_responses = [
        GenerationResponse("bad json", "model", "v1"),
        GenerationResponse("bad json again", "model", "v1"),
    ]
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.error.code == "invalid_model_output"
    assert len(runtime.generation.requests) == 2
    assert len(runtime.repository.calls) == 2


async def test_transient_provider_retries_are_bounded(settings, runtime):
    runtime.generation.analyze_responses = [ProviderError(transient=True) for _ in range(3)]
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.FAILED and run.error.code == "provider_error"
    assert len(runtime.generation.requests) == 3


async def test_truncated_response_is_not_a_success_or_a_repair(settings, runtime):
    runtime.generation.analyze_responses = [
        GenerationResponse(
            '{"schemaVersion":1,"title":"test"}',
            "model",
            "v1",
            finish_reason="length",
        )
    ]
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    assert (await runtime.repository.get_run(queued.id)).error.code == "truncated_response"
    assert len(runtime.generation.requests) == 1
    assert not runtime.repository.packages


async def test_missing_other_owners_templates_saves_real_stage_outputs_then_fails(
    settings, runtime
):
    (settings.templates_root / "angular-pwa" / "README.md").unlink()
    (settings.templates_root / "angular-pwa").rmdir()
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.error.code == "template_missing"
    assert Storage(settings).path(f"{run.id}/steps/design/001/output.json").is_file()
    assert not runtime.repository.packages


async def test_deploy_failure_keeps_generated_success_and_truthful_deployment_status(
    settings, runtime
):
    class BrokenDeployer:
        async def deploy(self, run_id, workspace):
            raise RuntimeError("deploy SECRET")

    runtime.deployer = BrokenDeployer()
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.SUCCEEDED and run.error is None
    assert run.deployment_status == DeploymentStatus.FAILED and run.preview_url is None
    steps = await runtime.repository.list_steps(run.id)
    deploy = next(step for step in steps if step.key == "deploy")
    assert deploy.status == StepStatus.FAILED and "SECRET" not in deploy.error.message


@pytest.mark.parametrize("failure", ["deadline", "lost_heartbeat", "shutdown"])
async def test_worker_interruptions_cancel_inflight_generation(settings, runtime, failure):
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def blocked_generation(request):
        started.set()
        try:
            await asyncio.sleep(30)
        finally:
            stopped.set()

    runtime.generation.generate = blocked_generation
    settings = settings.model_copy(
        update={
            "heartbeat_seconds": 0.01,
            "stale_seconds": 0.05,
            "run_timeout_seconds": 0.1 if failure == "deadline" else 30,
        }
    )
    runtime.repository.heartbeat_ok = failure != "lost_heartbeat"
    queued = await queued_run(runtime.repository)
    task = asyncio.create_task(Worker(runtime, settings).run_once())
    await started.wait()
    if failure == "shutdown":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await task
    assert stopped.is_set()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.FAILED
    assert run.error.code == ("run_timeout" if failure == "deadline" else "worker_interrupted")
    assert not runtime.repository.packages


def test_worker_refuses_to_start_without_real_integration(settings, runtime):
    runtime.generation = None
    with pytest.raises(AppError, match="not_ready"):
        Worker(runtime, settings)


async def test_api_contract_cannot_be_changed_by_repair(settings, runtime):
    runtime.validator.failures = 1
    original = runtime.generation.generate

    async def tamper(request):
        response = await original(request)
        if request.stage == "repair":
            payload = {
                "schemaVersion": 1,
                "files": [{"path": "system-spec.json", "content": "{}"}],
                "notes": [],
            }
            return replace(response, content=json.dumps(payload))
        return response

    runtime.generation.generate = tamper
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    assert (await runtime.repository.get_run(queued.id)).error.code == "unsafe_file"
    assert not runtime.repository.packages


async def test_absent_runner_never_produces_a_successful_package(settings, runtime):
    runtime.validator = None
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.FAILED and run.error.code == "not_ready"
    assert not runtime.repository.packages
    assert Storage(settings).path(f"{run.id}/steps/analyze/001/output.json").is_file()


async def test_runner_must_not_mutate_or_add_files_to_immutable_workspace(settings, runtime):
    original = runtime.validator.validate

    async def mutate(workspace):
        report = await original(workspace)
        root = Storage(settings).path(workspace.files[0].path).parent
        (root / "injected.cs").write_text("unexpected")
        return report

    runtime.validator.validate = mutate
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == RunStatus.FAILED and run.error.code == "artifact_corrupt"
    assert not runtime.repository.packages
