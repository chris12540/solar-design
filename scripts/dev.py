"""Start API and UI locally; Ctrl-C stops both without stopping PostgreSQL."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def environment():
    path = ROOT / ".env"
    if not path.exists():
        raise SystemExit("Missing .env. Run python3 scripts/local_db.py start first.")
    values = {}
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return {**values, **os.environ}


def main():
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():
        raise SystemExit("Missing .venv. Follow README setup instructions.")
    commands = [
        ([str(python), "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8000"], ROOT),
        (["npm", "run", "dev"], ROOT / "frontend"),
    ]
    processes = []
    try:
        for command, cwd in commands:
            processes.append(subprocess.Popen(command, cwd=cwd, env=environment(), start_new_session=True))
        print("Solar Designer: http://127.0.0.1:5173 — Ctrl-C stops API and UI.", flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        raise SystemExit("A development server exited; stopping its companion.")
    except KeyboardInterrupt:
        pass
    finally:
        for p in processes:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        for p in processes:
            try:
                p.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()


if __name__ == "__main__":
    main()
