"""Import assessor source files using private local environment configuration."""
import subprocess
import sys
from pathlib import Path
from dev import environment

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(subprocess.call([str(ROOT / ".venv/bin/python"), "-m", "backend.import_data", "--data-dir", str(ROOT / "Data"), *sys.argv[1:]], cwd=ROOT, env=environment()))
