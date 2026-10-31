"""Real API -> worker -> provider -> runner -> ZIP check. Never substitutes adapters."""

import json
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

BASE = "http://127.0.0.1:8000"


def request(path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)


def main():
    project = request(
        "/api/v1/projects",
        {
            "name": "Employee requests integration check",
            "requirements": (
                "Create an employee request tracker. Each request has a title, description "
                "and status (new, in_progress, done). Users can create a request, list requests "
                "and update the status. Persist records in PostgreSQL. "
                "Include domain tests and documentation."
            ),
        },
    )
    run = request(f"/api/v1/projects/{project['id']}/runs", {}, {"Idempotency-Key": str(uuid4())})
    deadline = time.monotonic() + 2700
    while time.monotonic() < deadline:
        run = request(f"/api/v1/runs/{run['id']}")
        if run["status"] in ("succeeded", "failed"):
            break
        time.sleep(3)
    report = {
        "projectId": project["id"],
        "runId": run["id"],
        "status": run["status"],
        "validationStatus": run.get("validationStatus"),
        "error": run.get("error"),
    }
    if run["status"] != "succeeded" or run.get("validationStatus") != "passed":
        print(json.dumps(report))
        return 1
    target = Path("/app/generated/verification") / f"{run['id']}.zip"
    target.parent.mkdir(exist_ok=True)
    with urllib.request.urlopen(
        BASE + f"/api/v1/runs/{run['id']}/download", timeout=30
    ) as response:
        target.write_bytes(response.read(64 * 1024 * 1024))
    import zipfile

    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert "compose.yaml" in archive.namelist()
        validation = json.loads(archive.read("reports/validation.json"))
        assert validation["passed"] is True
    report["zipPath"] = str(target)
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
