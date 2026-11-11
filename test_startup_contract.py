"""Regression checks for the local Admin Console startup contract."""

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parent


def test_backend_and_proxy_share_port() -> None:
    backend = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    launcher = (ROOT / "run_admin_app.py").read_text(encoding="utf-8")
    vite = (ROOT / "vite.config.ts").read_text(encoding="utf-8")

    assert 'ADMIN_BACKEND_PORT", "8000"' in launcher
    assert 'os.environ.get("PORT", "8000")' in backend
    assert "http://127.0.0.1:8000" in vite
    assert '/api/health' in backend
    assert '/api/health' in launcher


def test_default_dev_command_starts_full_application() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["dev"] == "python run_admin_app.py"
    assert package["scripts"]["dev:frontend"] == "vite"


if __name__ == "__main__":
    test_backend_and_proxy_share_port()
    test_default_dev_command_starts_full_application()
    print("Admin startup contract checks passed.")
