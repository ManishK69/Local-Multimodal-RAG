# /// script
# requires-python = ">=3.12"
# ///
"""First-run setup and local process launcher for Local Multimodal RAG."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
WEB_ROOT = ROOT / "apps" / "web"
COMPOSE_FILE = ROOT / "infra" / "docker-compose.yml"
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
DATA_DIR = ROOT / "data"

DEFAULT_MODELS = ("nomic-embed-text", "qwen2.5:7b", "qwen2.5vl:7b")


def fail(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def step(title: str) -> None:
    print(f"\n==> {title}", flush=True)


def require(command: str, hint: str) -> str:
    path = shutil.which(command)
    if path is None:
        fail(f"{command} is not on PATH. {hint}")
    return path


def run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(cmd), flush=True)
    completed = subprocess.run(cmd, cwd=cwd, env=env)
    if completed.returncode != 0:
        fail(f"command failed ({completed.returncode}): {' '.join(cmd)}", completed.returncode)


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def merged_env() -> dict[str, str]:
    env = os.environ.copy()
    for key, value in load_env(ENV_FILE).items():
        env.setdefault(key, value)
    env["DATA_DIR"] = str(DATA_DIR)
    return env


def ensure_env_file() -> None:
    if ENV_FILE.exists():
        print(f"using existing {ENV_FILE}")
        return
    if not ENV_EXAMPLE.exists():
        fail(f"missing {ENV_EXAMPLE}")
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    text = text.replace("DATA_DIR=./data", f"DATA_DIR={DATA_DIR}")
    ENV_FILE.write_text(text, encoding="utf-8")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"wrote {ENV_FILE}")


def wait_port(host: str, port: int, label: str, timeout: float = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                print(f"{label} is ready on {host}:{port}")
                return
        except OSError:
            time.sleep(0.4)
    fail(f"timed out waiting for {label} at {host}:{port}")


def host_port(url: str, default_port: int) -> tuple[str, int]:
    parsed = urlparse(url.replace("postgresql+asyncpg", "postgresql", 1))
    return parsed.hostname or "127.0.0.1", parsed.port or default_port


def docker_up(env: dict[str, str]) -> None:
    step("Starting Postgres and Redis")
    run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"],
        cwd=ROOT,
        env=env,
    )
    pg_host, pg_port = host_port(env["POSTGRES_URL"], 5433)
    redis_host, redis_port = host_port(env["REDIS_URL"], 6379)
    wait_port(pg_host, pg_port, "Postgres")
    wait_port(redis_host, redis_port, "Redis")


def installed_ollama_models() -> set[str]:
    listing = subprocess.run(
        ["ollama", "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        fail("ollama list failed. Is Ollama running?")
    names: set[str] = set()
    for line in listing.stdout.splitlines():
        token = line.split()[0] if line.split() else ""
        if not token or token.lower() == "name":
            continue
        names.add(token)
    return names


def model_present(installed: set[str], model: str) -> bool:
    if model in installed or f"{model}:latest" in installed:
        return True
    prefix = model if ":" in model else f"{model}:"
    return any(item == model or item.startswith(prefix) for item in installed)


def pull_models(env: dict[str, str]) -> None:
    step("Checking Ollama models")
    models = (
        env.get("EMBED_MODEL") or DEFAULT_MODELS[0],
        env.get("GENERATE_MODEL") or DEFAULT_MODELS[1],
        env.get("VISION_MODEL") or DEFAULT_MODELS[2],
    )
    installed = installed_ollama_models()
    missing = [model for model in models if not model_present(installed, model)]
    if not missing:
        print("all required models are already present")
        return
    print("pulling", ", ".join(missing), "(this can take several minutes)")
    for model in missing:
        run(["ollama", "pull", model])


def sync_api(env: dict[str, str]) -> None:
    step("Installing API and applying migrations")
    run(["uv", "sync"], cwd=API_ROOT, env=env)
    run(["uv", "run", "alembic", "upgrade", "head"], cwd=API_ROOT, env=env)


def sync_web(env: dict[str, str]) -> None:
    step("Installing web dependencies")
    npm = require("npm", "Install Node 22 from https://nodejs.org/")
    run([npm, "install"], cwd=WEB_ROOT, env=env)


def pump(proc: subprocess.Popen[str], prefix: str) -> None:
    assert proc.stdout is not None
    for line in proc.stdout:
        print(f"{prefix} {line}", end="", flush=True)


def start_process(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    kwargs: dict[str, object] = {
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "bufsize": 1,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    print("$", " ".join(cmd), flush=True)
    return subprocess.Popen(cmd, **kwargs)


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(proc.pid, signal.SIGTERM)
    except OSError:
        proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def start_stack(env: dict[str, str]) -> None:
    step("Starting API, ingest worker, and web UI")
    uv = require("uv", "Install uv from https://docs.astral.sh/uv/")
    npm = require("npm", "Install Node 22 from https://nodejs.org/")
    children = [
        (
            "api",
            start_process(
                [uv, "run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
                cwd=API_ROOT,
                env=env,
            ),
        ),
        (
            "worker",
            start_process(
                [uv, "run", "arq", "app.worker.WorkerSettings"],
                cwd=API_ROOT,
                env=env,
            ),
        ),
        (
            "web",
            start_process([npm, "run", "dev"], cwd=WEB_ROOT, env=env),
        ),
    ]
    threads = [
        threading.Thread(target=pump, args=(proc, f"[{name}]"), daemon=True)
        for name, proc in children
    ]
    for thread in threads:
        thread.start()

    print("\nLibrary: http://127.0.0.1:3000/library")
    print("API:     http://127.0.0.1:8000/health")
    print("Ctrl+C stops the app. Docker (Postgres/Redis) stays running.\n", flush=True)

    try:
        while True:
            for name, proc in children:
                code = proc.poll()
                if code is not None:
                    fail(f"{name} exited with code {code}", code or 1)
            time.sleep(0.4)
    except KeyboardInterrupt:
        print("\nStopping API, worker, and web…", flush=True)
    finally:
        for _, proc in children:
            stop_process(proc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set up and run Local Multimodal RAG on localhost.",
    )
    parser.add_argument(
        "--setup-only",
        action="store_true",
        help="Install deps, start Docker, pull models, migrate; do not start the app.",
    )
    parser.add_argument(
        "--no-pull",
        action="store_true",
        help="Skip Ollama model downloads.",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Start the app without reinstalling deps or pulling models.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    step("Checking required tools")
    require("docker", "Install Docker Desktop and start it.")
    require("uv", "Install uv: https://docs.astral.sh/uv/getting-started/installation/")
    require("node", "Install Node 22: https://nodejs.org/")
    require("npm", "Install Node 22: https://nodejs.org/")
    require("ollama", "Install Ollama: https://ollama.com/download")

    if not args.skip_setup:
        ensure_env_file()
        env = merged_env()
        docker_up(env)
        if not args.no_pull:
            pull_models(env)
        sync_api(env)
        sync_web(env)
    else:
        if not ENV_FILE.exists():
            fail("missing .env — run once without --skip-setup")
        env = merged_env()
        docker_up(env)

    if args.setup_only:
        print("\nSetup complete. Start later with:")
        print("  uv run --script scripts/run_local.py --skip-setup")
        return

    start_stack(env)


if __name__ == "__main__":
    main()
