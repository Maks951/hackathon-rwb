import base64
import hashlib
import json
import re

from app.services.storage import relative_path

CHECKS = ("backend_build", "backend_tests", "admin_build", "pwa_build", "api_contract", "security")
MAX_REQUEST = 36 * 1024 * 1024


def digest_manifest(manifest):
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def unpack(payload):
    if not re.fullmatch(r"[0-9a-f-]{36}/00[0-2]", payload["workspaceId"]):
        raise ValueError("Invalid workspace ID")
    from uuid import UUID

    run, attempt = payload["workspaceId"].split("/")
    if str(UUID(run)) != run:
        raise ValueError("Noncanonical ID")
    prefix = f"{run}/workspaces/{attempt}/"
    manifest = payload["manifest"]
    if not 1 <= len(manifest) <= 500 or digest_manifest(manifest) != payload["manifestSha256"]:
        raise ValueError("Invalid manifest")
    files = {}
    names = set()
    for item in manifest:
        path = item["path"]
        if not path.startswith(prefix):
            raise ValueError("Foreign artifact")
        name = str(relative_path(path[len(prefix) :]))
        if name.casefold() in names or not 0 <= item["size_bytes"] <= 1048576:
            raise ValueError("Duplicate or oversized artifact")
        names.add(name.casefold())
        data = base64.b64decode(payload["files"][name], validate=True)
        if len(data) != item["size_bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Corrupt artifact")
        files[name] = data
    if set(payload["files"]) != set(files) or sum(map(len, files.values())) > 25165824:
        raise ValueError("Manifest mismatch or oversized tree")
    return files


def failed(message):
    return [{"name": n, "passed": False, "message": message} for n in CHECKS]
