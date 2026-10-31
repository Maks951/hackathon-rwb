"""Fixed checks inside a disposable, offline container. Never handles platform secrets."""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import Settings
from app.runner.protocol import MAX_REQUEST, failed, unpack
from app.services.storage import Storage, allowed_file

WORK = Path("/work/product")


def command(argv, cwd, timeout=120):
    with tempfile.TemporaryFile() as log:
        try:
            result = subprocess.run(
                argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False
            )
            log.seek(0, 2)
            size = log.tell()
            log.seek(max(0, size - 6000))
            message = log.read(6000).decode(errors="replace")
            # ANSI/control characters never reach UI/prompts.
            message = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", message)
            message = "".join(c for c in message if c in "\n\t" or c.isprintable())
            return result.returncode == 0, message or "Command completed."
        except (OSError, subprocess.TimeoutExpired):
            return False, "Command unavailable or timed out."


def security(files):
    trusted = Storage(Settings(_env_file=None, templates_root=Path("/opt/templates"))).templates()
    for name, data in trusted.items():
        if files.get(name) != data:
            return False, "Immutable template changed or missing: " + name
    denied = re.compile(
        r"(Process\s*\.\s*Start|DllImport|LibraryImport|Assembly\s*\.\s*Load|"
        r"Environment\s*\.\s*GetEnvironmentVariable|\beval\s*\(|"
        r"\bnew\s+Function\s*\(|child_process|/var/run/docker.sock)",
        re.I,
    )
    for name, data in files.items():
        if name in trusted or name in {
            "generated-api.json",
            "requirements-spec.json",
            "system-spec.json",
            "documentation-policy.json",
        }:
            continue
        if not allowed_file("repair", name):
            return False, "Unexpected generated path: " + name
        text = data.decode("utf-8")
        if denied.search(text):
            return False, "Forbidden execution/environment primitive in " + name
        if re.search(r"-----BEGIN .*PRIVATE KEY-----|\bsk-[A-Za-z0-9_\-]{16,}", text):
            return False, "Possible embedded secret in " + name
    return (
        True,
        "Immutable templates, paths, embedded-key and dangerous-primitive checks passed. "
        "Not a full security audit.",
    )


def trx_passed(path, minimum=1):
    root = ET.parse(path).getroot()
    counters = root.find(".//{*}Counters")
    return (
        counters is not None
        and int(counters.get("total", "0")) >= minimum
        and counters.get("passed") == counters.get("total")
    )


def validate(files):
    checks = []

    def add(name, result):
        checks.append(dict(name=name, passed=bool(result[0]), message=result[1][:8000]))

    safe = security(files)
    if not safe[0]:
        return failed(safe[1])
    WORK.mkdir(parents=True)
    for name, data in files.items():
        target = WORK / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    backend = WORK / "backend"
    restored = command(
        [
            "dotnet",
            "restore",
            "Generated.slnx",
            "--locked-mode",
            "--source",
            "/opt/nuget",
            "-p:NuGetAudit=false",
        ],
        backend,
    )
    build = (
        command(["dotnet", "build", "Generated.slnx", "--no-restore", "-c", "Release"], backend)
        if restored[0]
        else restored
    )
    add("backend_build", build)
    tests = (
        command(
            [
                "dotnet",
                "test",
                "Generated.slnx",
                "--no-build",
                "--no-restore",
                "-c",
                "Release",
                "--logger",
                "trx;LogFileName=tests.trx",
                "--results-directory",
                "/work/results",
            ],
            backend,
        )
        if build[0]
        else (False, "Backend build failed.")
    )
    if tests[0] and not list((backend / "tests/Generated.Api.Tests/Generated").rglob("*.cs")):
        tests = (False, "No generated domain tests were provided.")
    if tests[0]:
        try:
            tests = (trx_passed("/work/results/tests.trx", minimum=4), tests[1])
        except (OSError, ET.ParseError):
            tests = (False, "Test runner did not produce a valid TRX report.")
    add("backend_tests", tests)
    for folder, key in [("admin", "admin_build"), ("pwa", "pwa_build")]:
        shutil.copytree(
            "/opt/node-deps/node_modules", WORK / folder / "node_modules", symlinks=True
        )
        add(key, command(["node", "node_modules/@angular/cli/bin/ng.js", "build"], WORK / folder))
        shutil.rmtree(WORK / folder / "node_modules")
    # Compile a trusted test into a COPY, after domain tests have finished.
    if build[0]:
        test_path = backend / "tests/Generated.Api.Tests/RunnerContractTests.cs"
        shutil.copyfile("/opt/runner/RunnerContractTests.cs", test_path)
        result = command(
            [
                "dotnet",
                "test",
                "Generated.slnx",
                "--no-restore",
                "-c",
                "Release",
                "--filter",
                "FullyQualifiedName~RunnerContractTests",
                "--logger",
                "trx;LogFileName=contract.trx",
                "--results-directory",
                "/work/contract",
            ],
            backend,
        )
        if result[0]:
            try:
                result = (trx_passed("/work/contract/contract.trx"), result[1])
            except (OSError, ET.ParseError):
                result = (False, "Contract test report missing or invalid.")
    else:
        result = (False, "Backend build failed; runtime route discovery unavailable.")
    add("api_contract", result)
    add("security", safe)
    return checks


if __name__ == "__main__":
    os.environ.update(
        HOME="/tmp",
        DOTNET_CLI_HOME="/tmp",
        NUGET_PACKAGES="/opt/nuget",
        DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1",
        DOTNET_CLI_TELEMETRY_OPTOUT="1",
        NG_CLI_ANALYTICS="false",
        CI="true",
        ConnectionStrings__ProductDatabase="Host=127.0.0.1;Database=unavailable;Username=unavailable;Password=unavailable",
    )
    try:
        body = sys.stdin.buffer.read(MAX_REQUEST + 1)
        if len(body) > MAX_REQUEST:
            raise ValueError("Request too large")
        result = validate(unpack(json.loads(body)))
    except Exception:
        result = failed("Sandbox input, template integrity or validation execution failed.")
    print(json.dumps({"checks": result}))
