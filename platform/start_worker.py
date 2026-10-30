"""Run Yaroslav's existing worker against the SQL repository."""

import subprocess
import sys

from start_local import prepare

if __name__ == "__main__":
    prepare()
    subprocess.run([sys.executable, "-m", "app.worker"], check=True)
