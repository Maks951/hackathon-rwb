"""Run the integrated API; no worker is started in the API process."""

import os
import subprocess
import sys
from pathlib import Path


def prepare():
    os.chdir(Path(__file__).resolve().parent)
    os.environ.setdefault(
        "DATABASE_URL", "postgresql+psycopg://platform:platform_local@localhost:5432/platform"
    )
    root = os.environ.setdefault("GENERATED_ROOT", str(Path("generated").resolve()))
    os.environ.setdefault("RWB_GENERATED_ROOT", root)
    os.environ.setdefault("RWB_RUNTIME_FACTORY", "app.integrations.database_runtime:create_runtime")


if __name__ == "__main__":
    prepare()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--reload"], check=True)
