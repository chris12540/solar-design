"""Manage a project-local PostgreSQL cluster without a login-time service."""
import argparse
import os
from pathlib import Path
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
DATA = LOCAL / "postgres"
SOCKET = LOCAL / "socket"


def binaries():
    for candidate in (os.getenv("POSTGRES_BIN"), "/opt/homebrew/opt/postgresql@17/bin", "/usr/local/opt/postgresql@17/bin"):
        if candidate and (Path(candidate) / "initdb").exists():
            return Path(candidate)
    executable = shutil.which("initdb")
    if executable:
        return Path(executable).parent
    raise SystemExit("PostgreSQL 17 binaries missing. Install with brew install postgresql@17, or use compose.yaml.")


def load_env():
    values = {}
    if (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.strip() and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value
    return values


def run(command, **kwargs):
    subprocess.run(command, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop", "status"))
    args = parser.parse_args()
    bin_dir = binaries()
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    SOCKET.mkdir(mode=0o700, exist_ok=True)
    values = load_env()
    if args.action == "start":
        if not (ROOT / ".env").exists():
            password = secrets.token_urlsafe(24)
            values = {
                "DATABASE_URL": f"postgresql://solar_app:{password}@127.0.0.1:55432/solar_designer",
                "POSTGRES_PASSWORD": password,
                "STAFF_TOKEN": secrets.token_urlsafe(24),
                "SESSION_SECRET": secrets.token_urlsafe(32),
                "ALLOWED_ORIGINS": "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:8000",
            }
            descriptor = os.open(ROOT / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as f:
                f.write("".join(f"{key}={value}\n" for key, value in values.items()))
        if not (DATA / "PG_VERSION").exists():
            password = values.get("POSTGRES_PASSWORD")
            if not password:
                raise SystemExit("POSTGRES_PASSWORD missing from .env. Set it to match DATABASE_URL before initializing.")
            pwfile = LOCAL / "init-password"
            descriptor = os.open(pwfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                with os.fdopen(descriptor, "w") as f:
                    f.write(password)
                run([str(bin_dir / "initdb"), "-D", str(DATA), "-U", "solar_app", "-A", "scram-sha-256", "--pwfile", str(pwfile), "--locale=C", "-E", "UTF8"])
            finally:
                pwfile.unlink(missing_ok=True)
        status = subprocess.run([str(bin_dir / "pg_ctl"), "-D", str(DATA), "status"], capture_output=True)
        if status.returncode != 0:
            run([str(bin_dir / "pg_ctl"), "-D", str(DATA), "-l", str(LOCAL / "postgres.log"), "-o", f"-h 127.0.0.1 -p 55432 -k {SOCKET}", "start"])
        env = {**os.environ, "PGPASSWORD": values.get("POSTGRES_PASSWORD", "")}
        query = subprocess.run([str(bin_dir / "psql"), "-h", "127.0.0.1", "-p", "55432", "-U", "solar_app", "-d", "postgres", "-Atc", "SELECT 1 FROM pg_database WHERE datname='solar_designer'"], env=env, capture_output=True, text=True, check=True)
        if query.stdout.strip() != "1":
            run([str(bin_dir / "createdb"), "-h", "127.0.0.1", "-p", "55432", "-U", "solar_app", "solar_designer"], env=env)
        print("Project database ready on 127.0.0.1:55432. Local credentials stored in .env (not Git).")
    elif args.action == "stop":
        run([str(bin_dir / "pg_ctl"), "-D", str(DATA), "-m", "fast", "stop"])
    else:
        run([str(bin_dir / "pg_ctl"), "-D", str(DATA), "status"])


if __name__ == "__main__":
    main()
