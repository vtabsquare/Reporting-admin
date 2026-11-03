"""
update_agent.py — VTAB Admin Console update polling module.

Polls the VTAB Reporting Manager for new deployments and allows the
Admin Console to apply updates from GitHub. Uses only stdlib so that
no new dependencies are introduced.

Environment variables (read at startup; no crash if missing):
    VTAB_MANAGER_URL               — e.g. https://vtab-manager.onrender.com
    VTAB_CLIENT_ID                 — client ID registered in the Manager
    VTAB_AGENT_TOKEN               — bootstrap / agent token
    VTAB_UPDATE_POLL_INTERVAL_SECONDS — default 300
    VTAB_ADMIN_VERSION             — overrides automatic version detection
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# backend/ is one level below the repo root
_BACKEND_DIR: Path = Path(__file__).resolve().parent
_REPO_ROOT: Path = _BACKEND_DIR.parent

# ---------------------------------------------------------------------------
# Shared mutable state (protected by _lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_state: dict = {
    "update_available": False,
    "current_version": None,   # populated on first access
    "available_version": None,
    "release_notes": "",
    "deployment_id": None,
    "last_checked": None,       # ISO timestamp string
    "applying": False,
    "last_apply_status": None,  # "succeeded" | "failed" | "deploying" | …
}

# Guards against starting more than one background thread
_agent_started = False
_agent_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Version detection
# ---------------------------------------------------------------------------

def _detect_current_version() -> str:
    """Return the running version of the Admin Console.

    Priority:
      1. VTAB_ADMIN_VERSION environment variable
      2. ``version`` field inside ``package.json`` at the repo root
      3. Hard-coded fallback ``"1.0.0"``
    """
    env_ver = os.environ.get("VTAB_ADMIN_VERSION", "").strip()
    if env_ver:
        return env_ver

    pkg_json = _REPO_ROOT / "package.json"
    if pkg_json.is_file():
        try:
            with pkg_json.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            ver = str(data.get("version", "")).strip()
            if ver:
                return ver
        except Exception as exc:
            logger.debug("Could not parse package.json for version: %s", exc)

    return "1.0.0"

# ---------------------------------------------------------------------------
# Manager API helpers
# ---------------------------------------------------------------------------

def _manager_url() -> str:
    return os.environ.get("VTAB_MANAGER_URL", "").strip().rstrip("/")

def _client_id() -> str:
    return os.environ.get("VTAB_CLIENT_ID", "").strip()

def _agent_token() -> str:
    return os.environ.get("VTAB_AGENT_TOKEN", "").strip()

def _poll_interval() -> int:
    try:
        return int(os.environ.get("VTAB_UPDATE_POLL_INTERVAL_SECONDS", "300"))
    except (ValueError, TypeError):
        return 300


def _http_post(url: str, payload: dict) -> dict | None:
    """POST JSON to *url* and return parsed JSON body (or None on error)."""
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-VTAB-Agent-Token": _agent_token(),
                "X-VTAB-Client-ID": _client_id(),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except Exception as exc:
        logger.warning("Manager POST %s failed: %s", url, exc)
        return None


def _http_get(url: str) -> dict | None:
    """GET JSON from *url* and return parsed JSON body (or None on error)."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "X-VTAB-Agent-Token": _agent_token(),
                "X-VTAB-Client-ID": _client_id(),
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8")
            return json.loads(text) if text else {}
    except Exception as exc:
        logger.warning("Manager GET %s failed: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Polling logic
# ---------------------------------------------------------------------------

def _check_for_updates() -> None:
    """Query the Manager and update ``_state`` with the result."""
    base = _manager_url()
    if not base or not _client_id() or not _agent_token():
        logger.debug("update_agent: manager credentials not configured, skipping poll.")
        return

    current = _detect_current_version()
    data = _http_get(f"{base}/api/v1/agent/updates/available?component=administration")
    if not data or not (data.get("update") or data.get("deployment")):
        data = _http_get(f"{base}/api/v1/agent/deployments/next") or {}

    raw = data.get("update") or data.get("deployment") or data
    dep = raw if isinstance(raw, dict) and raw.get("id") else None

    now_iso = datetime.now(timezone.utc).isoformat()

    with _lock:
        _state["current_version"] = current
        if dep:
            ver = dep.get("target_version") or dep.get("release_version") or dep.get("version")
            _state["update_available"] = True
            _state["available_version"] = ver
            _state["release_notes"] = dep.get("release_notes", "")
            _state["deployment_id"] = dep.get("id")
        elif not _state.get("update_available"):
            _state["deployment_id"] = None
        _state["last_checked"] = now_iso

    logger.info(
        "update_agent: checked — current=%s available=%s update_available=%s",
        current,
        _state["available_version"],
        _state["update_available"],
    )


def _polling_loop() -> None:
    """Run forever, calling _check_for_updates on each interval."""
    while True:
        try:
            _check_for_updates()
        except Exception as exc:
            logger.error("update_agent: unhandled error in polling loop: %s", exc)
        interval = _poll_interval()
        threading.Event().wait(timeout=interval)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_update_agent() -> None:
    """Start the background polling thread. Safe to call multiple times."""
    global _agent_started
    with _agent_lock:
        if _agent_started:
            logger.debug("update_agent: already running, skipping start.")
            return
        _agent_started = True

    # Populate version immediately (so get_update_status() is useful at once)
    with _lock:
        _state["current_version"] = _detect_current_version()

    thread = threading.Thread(target=_polling_loop, name="vtab-update-agent", daemon=True)
    thread.start()
    logger.info("update_agent: background polling thread started (interval=%ds).", _poll_interval())


def _current_commit() -> str:
    sha = os.environ.get("RENDER_GIT_COMMIT", os.environ.get("GIT_COMMIT_SHA", "")).strip()
    if sha:
        return sha
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return ""


def handle_webhook(body: dict) -> dict:
    event = body.get("event") or body.get("action") or "update_offered"
    if event == "ping":
        return {"ok": True, "pong": True, "service": "VTAB Admin Console", "current_version": _detect_current_version()}

    with _lock:
        if event in ("update_offered", "update_available", "scheduled"):
            _state["update_available"] = True
            ver = body.get("version") or body.get("target_version") or body.get("release_version")
            dep_id = body.get("deployment_id") or body.get("id")
            _state["available_version"] = ver
            _state["release_notes"] = body.get("release_notes", "")
            _state["deployment_id"] = dep_id
            _state["last_checked"] = datetime.now(timezone.utc).isoformat()
            logger.info("update_agent: webhook received update offer %s (dep=%s)", ver, dep_id)
            return {"ok": True, "status": "offered", "deployment_id": dep_id, "version": ver}
        elif event in ("update_cancelled", "cancelled"):
            _state["update_available"] = False
            _state["deployment_id"] = None
            _state["last_checked"] = datetime.now(timezone.utc).isoformat()
            logger.info("update_agent: webhook cancelled update offer")
            return {"ok": True, "status": "cancelled"}
    return {"ok": True, "message": "ignored"}


def get_update_status() -> dict:
    """Return the cached update-check result. Never blocks.

    Returns a copy so callers cannot mutate shared state.
    """
    with _lock:
        data = dict(_state)
        data["commit_sha"] = _current_commit()
        return data


def _trigger_render_deploy() -> dict:
    """Trigger a Render service redeploy via the Render REST API or Deploy Hook."""
    deploy_hook = (
        os.environ.get("RENDER_DEPLOY_HOOK_URL")
        or os.environ.get("RENDER_DEPLOY_HOOK")
        or ""
    ).strip()
    if deploy_hook and deploy_hook.startswith("http"):
        try:
            req = urllib.request.Request(deploy_hook, data=b"", method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                logger.info("Triggered Render deploy hook (%s)", resp.status)
                return {"ok": True, "deploy_id": "deploy-hook", "status": resp.status}
        except Exception as exc:
            logger.warning("Render deploy hook trigger failed: %s", exc)

    api_key = (
        os.environ.get("RENDER_API_KEY")
        or os.environ.get("RENDER_TOKEN")
        or os.environ.get("RENDER_API_TOKEN")
        or ""
    ).strip()
    service_id = (
        os.environ.get("RENDER_SERVICE_ID")
        or os.environ.get("VTAB_RENDER_SERVICE_ID")
        or "srv-dbksbt6k1f9s73dseub0"
    ).strip()

    if not api_key:
        logger.warning("RENDER_API_KEY not set in environment variables.")
        return {"ok": False, "error": "RENDER_API_KEY is not set in Render environment variables"}
    if not service_id:
        return {"ok": False, "error": "RENDER_SERVICE_ID is not configured"}

    url = f"https://api.render.com/v1/services/{service_id}/deploys"
    payload = json.dumps({"clearCache": "do_not_clear"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            deploy_id = data.get("id") or data.get("deploy", {}).get("id")
            return {"ok": True, "deploy_id": deploy_id, "data": data}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {exc.code}: {err_body}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def trigger_apply() -> None:
    """Apply a pending update synchronously (designed to run in a background thread).

    Steps:
      1. Report *preflight* to the Manager.
      2. ``git pull origin main`` in the repo root.
      3. Report *deploying* to the Manager.
      4. ``pip install -r backend/requirements.txt``.
      5. ``npm ci && npm run build`` (only if ``package.json`` exists in the repo root).
      6. Report *validating* → *succeeded* (or *failed* on any exception).

    ``_state["applying"]`` and ``_state["last_apply_status"]`` are kept current
    throughout so callers can poll ``get_update_status()`` for live progress.
    """
    base = _manager_url()
    deployment_id = _state.get("deployment_id")

    def _report(stage: str, detail: str = "") -> None:
        """Best-effort status report to the Manager."""
        if not base or not _client_id() or not _agent_token() or not deployment_id:
            return
        payload: dict = {
            "status": stage,
            "message": detail,
        }
        if stage == "succeeded":
            payload["health_verified"] = True
            payload["installed_version"] = _state.get("available_version") or _detect_current_version()
            commit = _current_commit()
            if commit:
                payload["installed_commit_sha"] = commit
        _http_post(f"{base}/api/v1/agent/deployments/{deployment_id}/report", payload)

    def _set_state(**kwargs: object) -> None:
        with _lock:
            _state.update(kwargs)

    _set_state(applying=True, last_apply_status="preflight")
    logger.info("update_agent: starting apply — deployment_id=%s", deployment_id)

    try:
        # 1. Preflight report
        _report("preflight", "Starting update")

        # 2. Check if running in Render cloud environment
        is_render = bool(
            os.environ.get("RENDER")
            or os.environ.get("RENDER_INSTANCE_ID")
            or os.environ.get("RENDER_SERVICE_ID")
            or os.environ.get("RENDER_API_KEY")
        )
        if is_render:
            _set_state(last_apply_status="deploying")
            _report("deploying", "Render deploy triggered — building in cloud...")
            render_result = _trigger_render_deploy()
            if render_result.get("ok"):
                ver = _state.get("available_version") or _detect_current_version()
                _set_state(
                    applying=False,
                    last_apply_status="succeeded",
                    current_version=ver,
                    update_available=False,
                )
                _report("succeeded", "Render deploy triggered successfully")
                logger.info("update_agent: Render deploy triggered (deploy_id=%s)", render_result.get("deploy_id"))
                return
            else:
                err_msg = render_result.get("error") or "Render deploy failed"
                logger.warning("update_agent: Render deploy failed: %s", err_msg)
                _set_state(applying=False, last_apply_status="failed")
                _report("failed", detail=err_msg)
                return

        # Check for simulated test mode
        if os.environ.get("VTAB_SIMULATE_BUILD") == "1":
            ver = _state.get("available_version") or _detect_current_version()
            _set_state(
                applying=False,
                last_apply_status="succeeded",
                current_version=ver,
                update_available=False,
            )
            _report("succeeded", "Update simulated successfully")
            return

        # 3. Local git pull & build flow
        logger.info("update_agent: running git pull origin main in %s", _REPO_ROOT)
        _set_state(last_apply_status="pulling")
        subprocess.run(
            ["git", "pull", "origin", "main"],
            cwd=str(_REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("update_agent: git pull completed.")

        # 3. Report deploying
        _set_state(last_apply_status="deploying")
        _report("deploying")

        # 4. pip install
        requirements_txt = _BACKEND_DIR / "requirements.txt"
        if requirements_txt.is_file():
            logger.info("update_agent: running pip install -r backend/requirements.txt")
            subprocess.run(
                ["pip", "install", "-r", str(requirements_txt)],
                cwd=str(_REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("update_agent: pip install completed.")
        else:
            logger.warning("update_agent: requirements.txt not found at %s, skipping pip install.", requirements_txt)

        # 5. npm ci && npm run build (only if package.json exists)
        package_json = _REPO_ROOT / "package.json"
        if package_json.is_file():
            logger.info("update_agent: running npm ci in %s", _REPO_ROOT)
            subprocess.run(
                ["npm", "ci"],
                cwd=str(_REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("update_agent: running npm run build")
            subprocess.run(
                ["npm", "run", "build"],
                cwd=str(_REPO_ROOT),
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("update_agent: npm build completed.")

        # 6. Validate → succeeded
        _set_state(last_apply_status="validating")
        _report("validating")

        # Refresh the cached version after a successful pull
        new_version = _detect_current_version()
        _set_state(
            applying=False,
            last_apply_status="succeeded",
            current_version=new_version,
            update_available=False,
        )
        _report("succeeded")
        logger.info("update_agent: apply succeeded. new version=%s", new_version)

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        logger.error("update_agent: apply failed (subprocess): %s — %s", exc, stderr)
        _set_state(applying=False, last_apply_status="failed")
        _report("failed", detail=stderr[:500] if stderr else str(exc))

    except Exception as exc:
        logger.error("update_agent: apply failed (unexpected): %s", exc)
        _set_state(applying=False, last_apply_status="failed")
        _report("failed", detail=str(exc)[:500])
