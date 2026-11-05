# VTAB Administration Console — End-to-End Update Workflow Implementation Guide

This guide documents the implementation of the centralized update lifecycle for the **VTAB Administration Console** (`Reporting-admin`), matching the exact workflow implemented for **Reporting Services** (`Reportingtool-webservice`).

---

## 1. Architectural Overview

```
┌─────────────────────────────────┐
│     VTAB Reporting Manager      │
│ (https://manager...nip.io)      │
└──────────────┬──────────────────┘
               │ 1. POST /api/update/webhook (update_offered)
               │    with {version, commit_sha, deployment_id}
               ▼
┌─────────────────────────────────┐
│     VTAB Administration API     │ ◄─── 2. Polling every 5s / status checks
│     (FastAPI on Port 8835)      │
└──────────────┬──────────────────┘
               │ 3. State stored in data/update-agent-state.json
               │    Exposes /api/update/status to React SPA
               ▼
┌─────────────────────────────────┐
│      Admin Frontend (SPA)       │ ───► 4. User sees top update banner:
│ (http://admin-reporting...nip.io)│      "Update available: Administration <version>"
└──────────────┬──────────────────┘      Clicks [Update Now]
               │ 5. POST /api/update/apply
               ▼
┌─────────────────────────────────┐
│      PixelBuildScreen (UI)      │ ───► 6. Real-time 8-bit build progress
│       + Local Git & Build       │      - Reports preflight & deploying to Manager
│                                 │      - git reset --hard origin/main
│                                 │      - npm run build (updates dist/)
│                                 │      - Reports succeeded to Manager
│                                 │      - Restarts reportingtool-admin.service
│                                 │      - Automatically hard reloads (?_v=...)
└─────────────────────────────────┘
```

---

## 2. Key Changes Made

### A. Manager Application (`VTAB Reporting Manager`)
1. **Endpoint Resolution (`manager/main.py`)**:
   - Updated `resolve_client_webhook_endpoints()` so that when `component == "administration"`, Manager automatically dispatches update webhooks to:
     - `http://admin-reporting.139.59.32.39.nip.io`
     - `http://admin-reporting.vtabsquare.com`
     - `http://127.0.0.1:8835` (backend port)
   - Updated periodic status polling to query `/api/update/status` (or `/api/v1/update/status`) on the client and verify `current_commit_sha` against `target_sha`.
   - Updated `effective_url` logic when marking a deployment succeeded to preserve `admin_url`.
2. **Security & Tokens (`manager/security.py`)**:
   - `verify_agent()` now recognizes both configured database tokens and standard connector tokens (`SDCsfIsSnlOj4ceWprbj-0GrsjxESrOT1DnmNJOGa_Y`).
3. **Database Configuration (`vtab_manager.db`)**:
   - Updated `clients.admin_url` for VTAB (`65805eab-d112-4b8f-b46d-a8f2dcd8cf0b`) to `http://admin-reporting.139.59.32.39.nip.io`.
   - Added `client_infrastructure` row for `component = 'administration'`, `provider = 'digitalocean'`, `status = 'active'`.

### B. Admin Backend (`Reporting-admin/backend`)
1. **Update Agent (`backend/update_agent.py`)**:
   - **Persistent State**: Maintains `backend/data/update-agent-state.json` so state survives restarts.
   - **Dual Environment Support**:
     - *DigitalOcean / Self-Hosted*: Runs `git fetch origin && git reset --hard origin/main`, runs `pip install -r backend/requirements.txt`, runs `npm run build`, updates state, and schedules graceful service reload (`systemctl restart reportingtool-admin.service`).
     - *Render Cloud*: Dispatches to Render API / Deploy Hook if environment variables indicate Render container.
   - **Supported Webhook Events**:
     - `update_offered` / `update_available` / `scheduled`
     - `update_cancelled` / `cancelled` (clears banner and resets status)
     - `update_completed` / `completed`
     - `ping` (healthcheck)
2. **API Endpoints (`backend/main.py`)**:
   - `GET /api/update/status` & `GET /api/v1/update/status`: Returns current version, commit SHA, update availability, and live apply status.
   - `POST /api/update/apply` & `POST /api/v1/update/apply`: Triggers update deployment in background thread.
   - `POST /api/update/webhook` & `POST /api/v1/update/webhook` & `POST /api/v1/update/offer`: Handles Manager notifications.
   - `POST /api/update/cancel` & `POST /api/v1/update/cancel`: Handles cancellation.
   - `POST /api/update/complete` & `POST /api/v1/update/complete`: Handles completion confirmation.
   - Dual authentication: accepts either valid admin Bearer token or `X-VTAB-Agent-Token`.

### C. Admin Frontend (`Reporting-admin/src`)
1. **Update Banner (`src/App.tsx`)**:
   - Shows top green notification banner with glowing status dot:
     `Update available: Administration <version>`
   - Prominent green **Update Now** button.
   - Listens to `/api/update/status` polling every 5s; instantly shows or hides banner when Manager offers or cancels an update.
2. **Build Screen (`src/PixelBuildScreen.tsx`)**:
   - Retro 8-bit chunky pixel build screen opens upon clicking **Update Now**.
   - Streams telemetry logs and milestone progress.
   - Detects completion (`status === "completed"` or `last_apply_status === "succeeded"`), displays victory sparkles, and performs a hard cache-busting reload (`window.location.href = ...?_v=<timestamp>`).

---

## 3. Environment Variables (`backend/.env`)

Add the following to `/var/www/reportingtool-admin/backend/.env`:

```env
# VTAB Reporting Manager Update Agent Configuration
VTAB_MANAGER_URL=https://manager.139.59.32.39.nip.io
VTAB_CLIENT_ID=65805eab-d112-4b8f-b46d-a8f2dcd8cf0b
VTAB_AGENT_TOKEN=SDCsfIsSnlOj4ceWprbj-0GrsjxESrOT1DnmNJOGa_Y
VTAB_UPDATE_POLL_INTERVAL_SECONDS=5
```

---

## 4. Verification Checklist

1. **Offer Update**:
   - Go to Manager (`https://manager.139.59.32.39.nip.io`).
   - Create deployment for Client: **VTAB**, Component: **administration**, Release: select target approved release.
   - Manager status displays **Offered**.
   - Open Admin Console (`http://admin-reporting.139.59.32.39.nip.io`): green update banner appears at top.
2. **Cancel Update**:
   - In Manager, click **Cancel**.
   - Manager moves status to **Cancelled**.
   - Admin Console banner disappears immediately.
3. **Apply Update**:
   - In Admin Console, click **Update Now**.
   - `PixelBuildScreen` displays live build progress.
   - Backend pulls origin/main and compiles frontend `dist/`.
   - On completion, page reloads with fresh assets.
   - Manager automatically transitions deployment status to **Completed**.
