"""Start the VTAB Admin Console and prepare first-run dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
VENV_DIR = BACKEND_DIR / ".venv"
VENV_PYTHON = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
VITE = ROOT / "node_modules" / ".bin" / ("vite.cmd" if os.name == "nt" else "vite")
NPM = "npm.cmd" if os.name == "nt" else "npm"
BACKEND_HOST = os.environ.get("ADMIN_BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("ADMIN_BACKEND_PORT", "8000"))
FRONTEND_HOST = os.environ.get("ADMIN_FRONTEND_HOST", "127.0.0.1")
FRONTEND_PORT = int(os.environ.get("ADMIN_FRONTEND_PORT", "5173"))


def run_setup(command: list[str], cwd: Path, description: str) -> None:
    print(f"\n{description}...")
    completed = subprocess.run(command, cwd=cwd, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{description} failed (exit code {completed.returncode}).")


def prepare_backend() -> None:
    if not VENV_PYTHON.exists():
        run_setup(
            [sys.executable, "-m", "venv", str(VENV_DIR)],
            ROOT,
            "Creating the private Python environment",
        )

    dependency_check = subprocess.run(
        [
            str(VENV_PYTHON),
            "-c",
            "import fastapi, uvicorn, supabase, dotenv, httpx, pydantic",
        ],
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if dependency_check.returncode != 0:
        run_setup(
            [str(VENV_PYTHON), "-m", "pip", "install", "--upgrade", "pip"],
            BACKEND_DIR,
            "Preparing Python package installation",
        )
        run_setup(
            [str(VENV_PYTHON), "-m", "pip", "install", "-r", "requirements.txt"],
            BACKEND_DIR,
            "Installing backend packages",
        )


def prepare_frontend() -> None:
    if shutil.which(NPM) is None:
        raise RuntimeError(
            "Node.js/npm was not found. Install the current Node.js LTS release, "
            "restart the terminal, and run this file again."
        )
    if not VITE.exists():
        run_setup([NPM, "install"], ROOT, "Installing frontend packages")


def ensure_started(process: subprocess.Popen[bytes], name: str, seconds: float = 2.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"{name} stopped during startup (exit code {return_code}).")
        time.sleep(0.2)


def wait_for_backend(process: subprocess.Popen[bytes], timeout: float = 30.0) -> None:
    """Wait until the API is accepting requests, not merely until Python stays alive."""
    health_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/api/health"
    deadline = time.monotonic() + timeout
    last_error = "no response"
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(
                f"Admin backend stopped during startup (exit code {return_code})."
            )
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as response:
                if response.status == 200:
                    return
                last_error = f"HTTP {response.status}"
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = str(error)
        time.sleep(0.25)
    raise RuntimeError(
        f"Admin backend did not become ready at {health_url} within {timeout:.0f}s "
        f"({last_error})."
    )


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    print("=" * 50)
    print("VTAB ADMIN APPLICATION RUNNER")
    print(f"Directory: {ROOT}")
    print("=" * 50)

    try:
        prepare_backend()
        prepare_frontend()

        child_environment = os.environ.copy()
        child_environment["PYTHONUNBUFFERED"] = "1"
        child_environment["ADMIN_BACKEND_HOST"] = BACKEND_HOST
        child_environment["ADMIN_BACKEND_PORT"] = str(BACKEND_PORT)
        child_environment["PORT"] = str(BACKEND_PORT)

        print(f"\nStarting Admin Backend on http://{BACKEND_HOST}:{BACKEND_PORT}...")
        backend_process = subprocess.Popen(
            [str(VENV_PYTHON), "main.py"], cwd=BACKEND_DIR, env=child_environment
        )
        wait_for_backend(backend_process)

        print(f"Starting Admin Frontend on http://{FRONTEND_HOST}:{FRONTEND_PORT}...")
        frontend_process = subprocess.Popen(
            [
                NPM,
                "run",
                "dev:frontend",
                "--",
                "--host",
                FRONTEND_HOST,
                "--port",
                str(FRONTEND_PORT),
            ],
            cwd=ROOT,
            env=child_environment,
        )
        ensure_started(frontend_process, "Admin frontend")

        print("\n" + "-" * 50)
        print("ADMIN APPLICATION IS RUNNING:")
        print(f" - Frontend: http://{FRONTEND_HOST}:{FRONTEND_PORT}")
        print(f" - Backend:  http://{BACKEND_HOST}:{BACKEND_PORT}")
        print("Press Ctrl+C to stop both processes.")
        print("-" * 50)

        while backend_process.poll() is None and frontend_process.poll() is None:
            time.sleep(0.5)

        if backend_process.poll() is not None:
            raise RuntimeError(
                f"Admin backend stopped unexpectedly (exit code {backend_process.returncode})."
            )
        raise RuntimeError(
            f"Admin frontend stopped unexpectedly (exit code {frontend_process.returncode})."
        )
    except KeyboardInterrupt:
        print("\nStopping Admin Application...")
        return 0
    except (OSError, RuntimeError) as error:
        print(f"\nSTARTUP FAILED: {error}", file=sys.stderr)
        print(
            "If this was the first run, confirm that the computer has internet access, "
            "Python and Node.js LTS are installed, then run the launcher again.",
            file=sys.stderr,
        )
        return 1
    finally:
        stop_process(frontend_process)
        stop_process(backend_process)
        print("Admin Application stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
