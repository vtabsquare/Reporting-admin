# VTAB Governance Console

Administrative control plane for VTAB Reporting Services.

## Included capabilities

- Governed user creation with first-login email verification.
- Team workspace creation, owner assignment and role management.
- Reusable access groups that synchronize their users into Services workspaces.
- Unified audit view for publishing, refreshes, data alerts and governance actions.
- Reporting Services support-ticket tracking.
- Token-verified administrator enrollment with `Admin` and read-only `Auditor` roles.
- Workspace notification-routing controls.

## Required database migration

Run `backend/supabase_migrations/001_admin_governance.sql` in the same Supabase project used by Reporting Services.

The migration creates governance, access-group and administrator-enrollment tables. Existing workspace memberships are registered as direct assignments so group removal cannot accidentally revoke them.

## Configuration

1. Copy `backend/.env.example` to `backend/.env`.
2. Enter the Supabase URL and service-role key.
3. Configure the Brevo API key and verified sender.
4. Set `ADMIN_EMAIL` to the first administrator's registered email.
5. Keep `ADMIN_MASTER_KEY` blank unless an explicit emergency key is required.

Never commit or redistribute `backend/.env`.

## Install and run

Install the current [Node.js LTS](https://nodejs.org/) release once, then launch with:

```powershell
python run_admin_app.py
```

The equivalent npm command is:

```powershell
npm run dev
```

Both commands start the API and frontend together. `npm run dev:frontend` is reserved
for frontend-only work when the API is already running separately.

On the first launch, the runner automatically creates `backend/.venv`, installs the
Python packages from `backend/requirements.txt`, and installs the frontend packages.
The initial setup therefore needs internet access and may take a few minutes. Later
launches reuse those local dependencies.

The runner reports the application as running only after both the backend and frontend
remain alive through their startup checks. If setup fails, read the `STARTUP FAILED`
message, correct the stated prerequisite, and run the same command again.

Frontend: `http://127.0.0.1:5173`

Backend API: `http://127.0.0.1:8000`

The launcher starts both the API and the browser application and waits for
`/api/health` before opening the frontend. Do not start only `npm run dev`, because
the browser application requires the Python API. To use another local API port,
set `ADMIN_BACKEND_PORT` and the matching `VITE_ADMIN_API_TARGET` before launching.

## Services integration

The Admin Console uses the same `workspaces`, `workspace_members`, users and audit tables as Reporting Services. Group assignments are materialized into `workspace_members`, so Services recognizes them immediately.

Apply the accompanying Services update to preserve direct assignments when users also receive access through groups.
