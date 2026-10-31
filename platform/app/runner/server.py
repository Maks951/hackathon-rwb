"""Trusted Docker broker. Never execute model commands in this process."""

import hmac
import json
import os
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from app.errors import AppError
from app.runner.protocol import MAX_REQUEST, failed, unpack

GATE = threading.BoundedSemaphore(1)


def run_container(payload):
    name = "rwb-validation-" + uuid4().hex
    image = os.environ.get("RWB_SANDBOX_IMAGE", "localhost/rwb-sandbox:dev")
    timeout = int(os.environ.get("RWB_RUNNER_TIMEOUT_SECONDS", "600"))
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--pids-limit",
        "256",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--user",
        "10001:10001",
        "--tmpfs",
        "/work:rw,nosuid,nodev,size=1073741824,uid=10001,gid=10001",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=268435456,uid=10001,gid=10001",
        "--log-driver",
        "none",
        image,
    ]
    with tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as out:
        inp.write(json.dumps(payload).encode())
        inp.seek(0)
        process = None
        try:
            process = subprocess.Popen(command, stdin=inp, stdout=out, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + timeout
            while process.poll() is None:
                if time.monotonic() > deadline or os.fstat(out.fileno()).st_size > 65536:
                    raise TimeoutError()
                time.sleep(0.2)
            out.seek(0)
            if process.returncode != 0:
                return failed(
                    "Sandbox failed to start or terminated; inspect runner image and resources."
                )
            result = json.loads(out.read(65537))
            return result["checks"]
        except (OSError, ValueError, KeyError, TimeoutError):
            return failed("Sandbox timed out, exceeded limits or produced an invalid report.")
        finally:
            # Only this invocation's uniquely named sandbox may be removed.
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            if process is not None and process.poll() is None:
                process.kill()
                process.wait()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # No requests, tokens or generated content in access logs.

    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def do_POST(self):
        expected = "Bearer " + os.environ["RWB_RUNNER_TOKEN"]
        if self.path != "/validate" or not hmac.compare_digest(
            self.headers.get("Authorization", ""), expected
        ):
            self.send_error(403)
            return
        if not GATE.acquire(blocking=False):
            self.send_error(503)
            return
        try:
            self.connection.settimeout(20)
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST:
                raise ValueError()
            payload = json.loads(self.rfile.read(size))
            unpack(payload)  # Validate before asking Docker to do anything.
            checks = run_container(payload)
            body = json.dumps(
                dict(
                    workspaceId=payload["workspaceId"],
                    manifestSha256=payload["manifestSha256"],
                    checks=checks,
                )
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (AppError, ValueError, KeyError, TypeError, AttributeError, OSError):
            self.send_error(400, "Invalid validation request")
        finally:
            GATE.release()


if __name__ == "__main__":
    if len(os.environ.get("RWB_RUNNER_TOKEN", "")) < 32:
        raise SystemExit("RWB_RUNNER_TOKEN must contain at least 32 characters")
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
