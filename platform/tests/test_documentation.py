import json
import zipfile

import pytest

from app.services.documentation import check_documentation, load_policy
from app.services.storage import Storage
from app.worker import Worker
from tests.fakes import queued_run


async def generated_docs(runtime):
    from app.ports import GenerationRequest

    response = await runtime.generation.generate(
        GenerationRequest(
            "generate_tests_docs",
            {
                "documentationPolicy": load_policy().model_dump(mode="json"),
            },
        )
    )
    return {f["path"]: f["content"].encode() for f in json.loads(response.content)["files"]}


async def test_documentation_follows_source_templates_and_each_api_endpoint(runtime):
    files = await generated_docs(runtime)
    spec = {"endpoints": [{"id": "list", "method": "GET", "path": "/api/v1/tickets"}]}
    assert check_documentation(files, spec, load_policy()).passed
    spec["endpoints"].append({"id": "create", "method": "POST", "path": "/api/v1/tickets"})
    result = check_documentation(files, spec, load_policy())
    assert not result.passed and "POST /api/v1/tickets" in result.message


@pytest.mark.parametrize("mode", ["missing", "empty", "fenced", "commented", "no_fr"])
async def test_incomplete_or_example_only_docs_are_rejected(runtime, mode):
    files = await generated_docs(runtime)
    text = files["docs/system-analysis.md"].decode()
    if mode == "missing":
        del files["docs/adr.md"]
    elif mode == "empty":
        files["docs/system-analysis.md"] = b"## Frontend\n"
    elif mode == "fenced":
        files["docs/system-analysis.md"] = f"```markdown\n{text}\n```".encode()
    elif mode == "commented":
        files["docs/system-analysis.md"] = f"<!--\n{text}\n-->".encode()
    else:
        files["docs/system-analysis.md"] = text.replace("FR-1", "no identifier").encode()
    assert not check_documentation(files, {"endpoints": []}, load_policy()).passed


async def test_saved_policy_reaches_all_stages_and_archive_contains_actual_report(
    settings, runtime
):
    queued = await queued_run(runtime.repository)
    await Worker(runtime, settings).run_once()
    run = await runtime.repository.get_run(queued.id)
    assert run.status == "succeeded"
    assert all(
        r.inputs["documentationPolicy"]["policyVersion"] == "russtech-sa-2026-10-30"
        for r in runtime.generation.requests
    )
    artifact = runtime.repository.packages[run.id]
    with zipfile.ZipFile(Storage(settings).verified_path(artifact)) as archive:
        report = json.loads(archive.read("reports/validation.json"))
        assert report["passed"]
        assert "documentation" in {c["name"] for c in report["checks"]}
        assert report["sourceManifest"]
        assert json.loads(archive.read("documentation-policy.json"))["sources"]
