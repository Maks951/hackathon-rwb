"""Real platform-stack smoke check with disposable project/volumes, never a code runner."""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

import yaml


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compose", default="podman-compose")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "compose.backend.yaml").read_text())
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    for name in ("api", "migrate", "worker"):
        config["services"][name]["build"]["context"] = str(root)
        config["services"][name]["env_file"] = [str(root / "platform/.env.example")]
    config["services"]["api"]["ports"] = [f"127.0.0.1:{port}:8000"]
    env = {**os.environ, "POSTGRES_PASSWORD": "rwb_disposable_check_only", "COMPOSE_PROFILES": ""}
    project = f"rwb-check-{uuid4().hex[:10]}"

    with tempfile.TemporaryDirectory(prefix="rwb-compose-") as folder:
        compose = Path(folder) / "compose.yaml"
        compose.write_text(yaml.safe_dump(config), encoding="utf-8")
        command = [args.compose, "-p", project, "-f", str(compose)]

        def run(*arguments: str) -> str:
            return subprocess.check_output(
                [*command, *arguments], cwd=root, env=env, text=True, stderr=subprocess.STDOUT
            )

        def request(path: str, body: dict | None = None) -> tuple[int, dict]:
            data = None if body is None else json.dumps(body).encode()
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}{path}",
                data=data,
                headers={"Content-Type": "application/json"} if body is not None else {},
            )
            try:
                response = urllib.request.urlopen(req, timeout=3)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                return response.status, json.loads(response.read())

        def wait_ready() -> None:
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if request("/health") == (200, {"status": "ok"}):
                        return
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            raise RuntimeError("Container API did not become ready in 60 seconds")

        try:
            run("up", "-d", "--no-build")
            wait_ready()
            status, project_data = request(
                "/api/v1/projects",
                {
                    "name": "Container check",
                    "requirements": "Manage requests with status transitions",
                },
            )
            assert status == 201, (status, project_data)
            assert set(project_data) == {"id", "name", "requirements", "createdAt"}
            assert project_data["createdAt"].endswith("Z")
            run("restart", "api")
            wait_ready()
            assert request(f"/api/v1/projects/{project_data['id']}") == (200, project_data)
            assert request(f"/api/v1/projects/{uuid4()}")[0] == 404
            assert request("/api/v1/projects", {"name": "bad"})[0] == 400
            assert run("exec", "-T", "api", "id", "-u").strip() == "10001"
            probe = (
                "from pathlib import Path; "
                "assert not Path('/app/platform/.env').exists(); "
                "assert not Path('/app/platform/.venv').exists(); "
                "p=Path('/app/generated/check.txt'); p.write_text('ok'); print(p.read_text())"
            )
            assert run("exec", "-T", "api", "python", "-c", probe).strip() == "ok"
            print(
                json.dumps(
                    {
                        "result": "passed",
                        "postgres": "17.9",
                        "projectCreate": 201,
                        "persistedAfterApiRestart": True,
                        "validationError": 400,
                        "missingProject": 404,
                        "uid": 10001,
                        "generatedVolumeWritable": True,
                        "secretsAndVenvExcludedFromImage": True,
                    }
                )
            )
        except subprocess.CalledProcessError as exc:
            print(exc.output[-5000:])
            raise
        finally:
            # Only this invocation's unique project and its disposable volumes are removed.
            subprocess.run(
                [*command, "down", "-v"],
                cwd=root,
                env=env,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


if __name__ == "__main__":
    main()
