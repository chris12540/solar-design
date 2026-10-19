"""Run integration checks against the isolated test database."""
import subprocess
from pathlib import Path
from dev import environment

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    raise SystemExit(subprocess.call([str(ROOT / ".venv/bin/python"), "-m", "pytest", "backend/tests", "-q"], cwd=ROOT, env=environment()))
