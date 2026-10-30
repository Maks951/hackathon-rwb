"""Start local demo and apply migrations using this interpreter."""
import os
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://platform:platform_local@localhost:5432/platform")
    os.environ.setdefault("GENERATED_ROOT", str(Path("generated").resolve()))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "app.project_demo:app", "--reload"], check=True)
