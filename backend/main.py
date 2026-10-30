from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import time
import secrets
import hashlib
import json
from datetime import datetime, timezone, timedelta
import httpx
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = FastAPI(title="Admin Panel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "vitabsquare@gmail.com").lower().strip()
ADMIN_OTP_ENABLED = os.environ.get("ADMIN_OTP_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
BUILTIN_SUPER_ADMIN_EMAILS = {"vigneshrajas.vtab@gmail.com"}
SUPER_ADMIN_EMAILS = {
    ADMIN_EMAIL,
    *BUILTIN_SUPER_ADMIN_EMAILS,
    *(email.strip().lower() for email in os.environ.get("SUPER_ADMIN_EMAILS", "").split(",") if email.strip()),
}
SERVICES_API_URL = os.environ.get("SERVICES_API_URL", "http://127.0.0.1:8830/api/v1")
LOCAL_STUDIO_META = os.environ.get(
    "STUDIO_META_DB",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Reporting Tool Services", "data", "studio_meta.db"))
)

def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("Supabase credentials not configured in .env")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

_ADMIN_OTPS = {}
_ADMIN_SESSIONS = {}

def _issue_admin_session(email: str):
    token = "admin_token_" + secrets.token_urlsafe(32)
    admin = _admin_record(email)
    _ADMIN_SESSIONS[token] = {
        "email": email,
        "role": "Super Admin" if email in SUPER_ADMIN_EMAILS else (admin or {}).get("role", "Admin"),
        "user_id": (admin or {}).get("user_id"),
        "expires": time.time() + int(os.environ.get("ADMIN_SESSION_SECONDS", "28800")),
    }
    return token, admin

def send_brevo_email(to_email: str, subject: str, content: str):
    if not BREVO_API_KEY:
        raise ValueError("BREVO_API_KEY is not configured in .env")
    
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    data = {
        "sender": {"email": os.environ.get("VTAB_SMTP_FROM", "no-reply@vtab.com"), "name": "VTAB Admin"},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": content
    }
    response = httpx.post(url, headers=headers, json=data)
    if response.status_code >= 300:
        raise ValueError(f"Failed to send email: {response.text}")

class LoginRequest(BaseModel):
    email: str

class LoginVerify(BaseModel):
    email: str
    otp: str

class CreateUserReq(BaseModel):
    email: str
    displayName: str

class CreateWorkspaceReq(BaseModel):
    name: str
    owner_id: str

class AddMemberReq(BaseModel):
    workspace_id: str
    user_id: str
    role: str

@app.post("/api/auth/login-request")
def admin_login_request(req: LoginRequest):
    email = req.email.lower().strip()
    if not _is_allowed_admin_email(email):
        raise HTTPException(403, "Not authorized as admin.")

    # Temporary test mode: keep the OTP implementation available, but issue the
    # authenticated session immediately until ADMIN_OTP_ENABLED is turned on.
    if not ADMIN_OTP_ENABLED:
        token, admin = _issue_admin_session(email)
        if admin:
            try:
                get_supabase().table('platform_admins').update({'last_login_at': datetime.now(timezone.utc).isoformat()}).eq('user_id', admin['user_id']).execute()
            except Exception:
                pass
        return {"ok": True, "otp_required": False, "token": token}
    
    otp = f"{secrets.randbelow(1000000):06d}"
    _ADMIN_OTPS[email] = {
        'hash': hashlib.sha256(otp.encode()).hexdigest(),
        'expires': time.time() + 600
    }
    
    try:
        send_brevo_email(email, "Admin Panel Login OTP", f"Your Admin login OTP is: {otp}\n\nExpires in 10 minutes.")
    except Exception as e:
        raise HTTPException(400, str(e))
    
    return {"ok": True}

@app.post("/api/auth/login-verify")
def admin_login_verify(req: LoginVerify):
    email = req.email.lower().strip()
    record = _ADMIN_OTPS.get(email)
    if not record or time.time() > record['expires']:
        raise HTTPException(401, "OTP expired or invalid.")
    calc = hashlib.sha256(req.otp.encode()).hexdigest()
    if not secrets.compare_digest(calc, record['hash']):
        raise HTTPException(401, "Invalid OTP.")
    
    del _ADMIN_OTPS[email]
    token, admin = _issue_admin_session(email)
    if admin:
        try:
            get_supabase().table('platform_admins').update({'last_login_at': datetime.now(timezone.utc).isoformat()}).eq('user_id', admin['user_id']).execute()
        except Exception:
            pass
    return {"token": token, "ok": True}

def _admin_record(email: str):
    try:
        rows = get_supabase().table('platform_admins').select('*').eq('email', email.lower().strip()).eq('status', 'Active').limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None

def _is_allowed_admin_email(email: str) -> bool:
    # ADMIN_EMAIL is a one-time bootstrap path. Once the migration is installed,
    # all additional administrators must exist in platform_admins.
    return email in SUPER_ADMIN_EMAILS or _admin_record(email) is not None

def _require_admin(authorization: str | None, write: bool = False):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = authorization.split(" ", 1)[1]
    master_key = os.environ.get("ADMIN_MASTER_KEY", "").strip()
    if master_key and secrets.compare_digest(token, master_key):
        return {"email": ADMIN_EMAIL, "role": "Super Admin", "user_id": None}
    session = _ADMIN_SESSIONS.get(token)
    if not session or time.time() > session["expires"]:
        raise HTTPException(401, "Invalid or expired admin token")
    current = _admin_record(session["email"])
    if current:
        session.update({"role": "Super Admin" if session["email"] in SUPER_ADMIN_EMAILS else current.get("role", "Admin"), "user_id": current.get("user_id")})
    elif session["email"] not in SUPER_ADMIN_EMAILS:
        raise HTTPException(403, "Administrator access has been removed or suspended.")
    if write and session.get("role") == "Auditor":
        raise HTTPException(403, "Auditors have read-only access.")
    return session

def _audit(action: str, object_type: str, object_id: str | None, actor: dict | None, details: dict | None = None, workspace_id: str | None = None, result: str = "Success"):
    try:
        get_supabase().table('audit_logs').insert({
            'workspace_id': workspace_id,
            'actor_id': (actor or {}).get('user_id'),
            'action': action,
            'object_type': object_type,
            'object_id': object_id,
            'result': result,
            'details': details or {},
        }).execute()
    except Exception as error:
        print(f"Audit write skipped for {action}: {error}", flush=True)

@app.get("/api/session")
def admin_session(authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization)
    return {"email": actor.get("email"), "role": actor.get("role"), "expires_at": actor.get("expires")}

def _ensure_user_personal_workspace(sb: Client, user_id: str, email: str, display_name: str | None = None):
    """Ensure a user has an entry in vtab_users and their personal My Workspace."""
    clean_email = email.lower().strip()
    try:
        sb.table('vtab_users').upsert({
            'id': user_id,
            'email': clean_email,
            'display_name': display_name or clean_email.split('@')[0],
        }).execute()
    except Exception as e:
        print(f"Warning: Failed to upsert vtab_users for {clean_email}: {e}", flush=True)

    try:
        existing = sb.table('workspaces').select('id, name, is_personal').eq('created_by', user_id).eq('is_personal', True).limit(1).execute()
        if existing.data:
            ws_id = existing.data[0]['id']
            sb.table('workspace_members').upsert({
                'workspace_id': ws_id,
                'user_id': user_id,
                'role': 'Admin'
            }).execute()
            return ws_id

        # Organization
        membership = sb.table('organization_members').select('organization_id').eq('user_id', user_id).order('created_at').limit(1).execute()
        org_id = membership.data[0].get('organization_id') if membership.data else None
        if not org_id:
            owned = sb.table('organizations').select('id').eq('created_by', user_id).order('created_at').limit(1).execute()
            org_id = owned.data[0].get('id') if owned.data else None
        if not org_id:
            base_name = (clean_email.split('@', 1)[0] or 'VTAB').strip()
            org_res = sb.table('organizations').insert({
                'name': f"{base_name}'s Organization",
                'slug': f"org-{str(user_id).replace('-', '')}",
                'created_by': user_id,
            }).execute()
            org_id = org_res.data[0].get('id') if org_res.data else None
            if org_id:
                sb.table('organization_members').upsert({
                    'organization_id': org_id,
                    'user_id': user_id,
                    'role': 'Owner',
                }).execute()

        ws_res = sb.table('workspaces').insert({
            'name': 'My Workspace',
            'description': 'Private workspace',
            'created_by': user_id,
            'owner_id': user_id,
            'organization_id': org_id,
            'is_personal': True,
        }).execute()
        ws_id = ws_res.data[0].get('id') if ws_res.data else None
        if ws_id:
            sb.table('workspace_members').upsert({
                'workspace_id': ws_id,
                'user_id': user_id,
                'role': 'Admin',
            }).execute()
        return ws_id
    except Exception as e:
        print(f"Warning: Failed to ensure personal workspace for {clean_email}: {e}", flush=True)
        return None

@app.get("/api/users")
def get_users(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    res = sb.table('vtab_users').select('id, email, display_name').execute()
    admins = sb.table('platform_admins').select('user_id,role,status').execute().data or []
    admin_map = {row['user_id']: row for row in admins}
    group_members = sb.table('user_group_members').select('user_id,group_id').execute().data or []
    return {"users": [{**user, 'admin': admin_map.get(user['id']), 'group_count': len([m for m in group_members if m['user_id'] == user['id']])} for user in (res.data or [])]}

@app.post("/api/users/create")
def create_user(req: CreateUserReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    
    temp_password = secrets.token_urlsafe(16) + "A1!"
    otp = f"{secrets.randbelow(1000000):06d}"
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    otp_expires = time.time() + 86400 * 7
    
    res = sb.auth.admin.create_user({
        "email": req.email.lower().strip(),
        "password": temp_password,
        "email_confirm": True,
        "user_metadata": {
            "display_name": req.displayName,
            "first_login_otp_hash": otp_hash,
            "first_login_otp_expires": otp_expires
        }
    })
    
    user = res.user
    if not user:
        raise HTTPException(500, "Failed to create user in Supabase")

    # Auto-provision vtab_users mirror row and personal My Workspace
    _ensure_user_personal_workspace(sb, user.id, req.email, req.displayName)
    
    try:
        send_brevo_email(
            req.email,
            "Welcome to VTAB Reporting",
            f"Your account has been created.\nTo set up your password, use this OTP on your first login: {otp}"
        )
    except Exception as e:
        raise HTTPException(400, f"Failed to send email: {str(e)}")
        
    _audit('user.create', 'user', str(user.id), actor, {'email': req.email.lower().strip(), 'display_name': req.displayName})
    return {"ok": True, "user_id": user.id}

@app.post("/api/workspaces/create")
def admin_create_workspace(req: CreateWorkspaceReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(400, 'Workspace name is required.')
    
    user_id = req.owner_id
    membership = sb.table('organization_members').select('organization_id').eq('user_id', user_id).order('created_at').limit(1).execute()
    organization_id = membership.data[0].get('organization_id') if membership.data else None
    
    if not organization_id:
        owned = sb.table('organizations').select('id').eq('created_by', user_id).order('created_at').limit(1).execute()
        organization_id = owned.data[0].get('id') if owned.data else None
        
    if not organization_id:
        profile = sb.table('vtab_users').select('email').eq('id', user_id).limit(1).execute()
        email = profile.data[0].get('email') if profile.data else ''
        base_name = (str(email).split('@', 1)[0] or 'VTAB').strip()
        organization = sb.table('organizations').insert({
            'name': f"{base_name}'s Organization",
            'slug': f"org-{str(user_id).replace('-', '')}",
            'created_by': user_id,
        }).execute()
        organization_id = organization.data[0].get('id') if organization.data else None
        if organization_id:
            sb.table('organization_members').upsert({
                'organization_id': organization_id,
                'user_id': user_id,
                'role': 'Owner',
            }).execute()
            
    if not organization_id:
        raise HTTPException(500, 'Could not resolve an organization for this workspace.')

    res = sb.table('workspaces').insert({
        'name': clean_name,
        'created_by': user_id,
        'owner_id': user_id,
        'organization_id': organization_id,
        'is_personal': False,
    }).execute()
    ws = res.data[0] if res.data else {}
    ws_id = ws.get('id')
    
    sb.table('workspace_members').upsert({
        'workspace_id': ws_id,
        'user_id': user_id,
        'role': 'Admin',
    }).execute()
    try:
        sb.table('workspace_direct_members').upsert({'workspace_id': ws_id, 'user_id': user_id, 'role': 'Admin'}).execute()
    except Exception:
        pass

    # Also ensure system admin accounts have Admin access to all created workspaces
    admin_emails = SUPER_ADMIN_EMAILS | {"harishkadhi18022001@gmail.com", "vitabsquare@gmail.com"}
    for a_email in admin_emails:
        if a_email:
            admin_prof = sb.table('vtab_users').select('id').eq('email', a_email.strip().lower()).limit(1).execute()
            if admin_prof.data and admin_prof.data[0].get('id') != user_id:
                sb.table('workspace_members').upsert({
                    'workspace_id': ws_id,
                    'user_id': admin_prof.data[0]['id'],
                    'role': 'Admin',
                }).execute()
    
    _audit('workspace.create', 'workspace', str(ws_id), actor, {'name': clean_name, 'owner_id': user_id}, str(ws_id))
    return {"ok": True, "workspace_id": ws_id}
@app.get("/api/workspaces")
def admin_get_workspaces(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    res = sb.table('workspaces').select('*').execute()
    # Exclude personal "My Workspace" entries, only include created team workspaces
    filtered = [
        w for w in (res.data or [])
        if not w.get('is_personal') and str(w.get('name') or '').strip().lower() != 'my workspace'
    ]
    users = sb.table('vtab_users').select('id,email,display_name').execute().data or []
    user_map = {row['id']: row for row in users}
    members = sb.table('workspace_members').select('workspace_id,user_id').execute().data or []
    group_grants = sb.table('workspace_group_grants').select('workspace_id,group_id').execute().data or []
    for workspace in filtered:
        owner_id = workspace.get('owner_id') or workspace.get('created_by')
        workspace['owner'] = user_map.get(owner_id)
        workspace['member_count'] = len({row['user_id'] for row in members if row['workspace_id'] == workspace['id']})
        workspace['group_count'] = len([row for row in group_grants if row['workspace_id'] == workspace['id']])
    return {"workspaces": filtered}

@app.post("/api/workspaces/members/add")
def admin_add_member(req: AddMemberReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    sb.table('workspace_members').upsert({
        'workspace_id': req.workspace_id,
        'user_id': req.user_id,
        'role': req.role
    }).execute()
    try:
        sb.table('workspace_direct_members').upsert({'workspace_id': req.workspace_id, 'user_id': req.user_id, 'role': req.role}).execute()
    except Exception:
        pass
    _audit('workspace.member.add', 'user', req.user_id, actor, {'role': req.role}, req.workspace_id)
    return {"ok": True}




@app.get("/api/workspaces/{workspace_id}/members")
def admin_get_workspace_members(workspace_id: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    res = sb.table('workspace_members').select('user_id, role').eq('workspace_id', workspace_id).execute()
    users_res = sb.table('vtab_users').select('id, email, display_name').execute()
    user_dict = {u['id']: u for u in users_res.data or []}
    direct_rows = sb.table('workspace_direct_members').select('user_id').eq('workspace_id', workspace_id).execute().data or []
    direct_ids = {row['user_id'] for row in direct_rows}
    group_links = sb.table('workspace_group_member_links').select('user_id,group_id').eq('workspace_id', workspace_id).execute().data or []
    groups = sb.table('user_groups').select('id,name').execute().data or []
    group_names = {row['id']: row['name'] for row in groups}
    ws_rows = sb.table('workspaces').select('id,name,owner_id,created_by,description').eq('id', workspace_id).limit(1).execute().data or []
    ws = ws_rows[0] if ws_rows else {}
    owner_id = ws.get('owner_id') or ws.get('created_by')
    member_permissions = {}
    try:
        parsed_description = json.loads(ws.get('description') or '{}')
        if isinstance(parsed_description, dict):
            member_permissions = parsed_description.get('member_ui_permissions') or {}
    except Exception:
        member_permissions = {}

    members = res.data or []
    if owner_id and str(owner_id) not in {str(member.get('user_id')) for member in members}:
        members.insert(0, {'user_id': owner_id, 'role': 'Owner', 'is_owner': True, 'access_sources': ['Owner']})

    permission_defaults = {
        'all_commands': True,
        'can_file': True,
        'can_home': True,
        'can_view': True,
        'can_share': True,
        'can_pdf': True,
        'can_ppt': True,
        'can_refresh': True,
        'can_subscribe': True,
        'can_alert': True,
        'can_download': True,
    }
    for m in members:
        uid = str(m['user_id'])
        if owner_id and uid == str(owner_id):
            m['is_owner'] = True
        u = user_dict.get(m['user_id'])
        if u:
            m['vtab_users'] = {'email': u['email'], 'display_name': u['display_name']}
        if 'access_sources' not in m:
            sources = []
            if m['user_id'] in direct_ids:
                sources.append('Direct')
            sources.extend(group_names.get(link['group_id'], 'Group') for link in group_links if link['user_id'] == m['user_id'])
            m['access_sources'] = sources or ['Direct']
        configured = member_permissions.get(uid) or {}
        m['ui_permissions'] = {key: bool(configured.get(key, default)) for key, default in permission_defaults.items()}

    return {"members": members}


class UpdateMemberUiPermissionsReq(BaseModel):
    all_commands: bool = True
    can_file: bool = True
    can_home: bool = True
    can_view: bool = True
    can_share: bool = True
    can_pdf: bool = True
    can_ppt: bool = True
    can_refresh: bool = True
    can_subscribe: bool = True
    can_alert: bool = True
    can_download: bool = True


@app.put("/api/workspaces/{workspace_id}/members/{user_id}/ui-permissions")
def admin_update_member_ui_permissions(workspace_id: str, user_id: str, req: UpdateMemberUiPermissionsReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    rows = sb.table('workspaces').select('id,description').eq('id', workspace_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(404, "Workspace not found")
    raw_description = rows[0].get('description') or ''
    try:
        description = json.loads(raw_description) if raw_description else {}
        if not isinstance(description, dict):
            description = {'text': str(raw_description)}
    except Exception:
        description = {'text': str(raw_description)}
    permissions = {
        'all_commands': bool(req.all_commands),
        'can_file': bool(req.can_file),
        'can_home': bool(req.can_home),
        'can_view': bool(req.can_view),
        'can_share': bool(req.can_share),
        'can_pdf': bool(req.can_pdf),
        'can_ppt': bool(req.can_ppt),
        'can_refresh': bool(req.can_refresh),
        'can_subscribe': bool(req.can_subscribe),
        'can_alert': bool(req.can_alert),
        'can_download': bool(req.can_download),
    }
    description.setdefault('member_ui_permissions', {})[str(user_id)] = permissions
    sb.table('workspaces').update({'description': json.dumps(description)}).eq('id', workspace_id).execute()
    _audit('workspace.member.ui_permissions', 'workspace', workspace_id, actor, {'target_user_id': user_id, 'permissions': permissions}, workspace_id)
    return {'ok': True, 'ui_permissions': permissions}

class BatchAddMembersReq(BaseModel):
    user_ids: list[str]
    role: str

@app.post("/api/workspaces/{workspace_id}/members/batch")
def admin_batch_add_members(workspace_id: str, req: BatchAddMembersReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    inserts = [{'workspace_id': workspace_id, 'user_id': uid, 'role': req.role} for uid in req.user_ids]
    if inserts:
        sb.table('workspace_members').upsert(inserts).execute()
        try:
            sb.table('workspace_direct_members').upsert(inserts).execute()
        except Exception:
            pass
    _audit('workspace.members.batch_add', 'workspace', workspace_id, actor, {'user_ids': req.user_ids, 'role': req.role}, workspace_id)
    return {"ok": True}

class UpdateMemberRoleReq(BaseModel):
    role: str

@app.put("/api/workspaces/{workspace_id}/members/{user_id}")
def admin_update_member_role(workspace_id: str, user_id: str, req: UpdateMemberRoleReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    sb.table('workspace_members').update({'role': req.role}).eq('workspace_id', workspace_id).eq('user_id', user_id).execute()
    try:
        sb.table('workspace_direct_members').upsert({'workspace_id': workspace_id, 'user_id': user_id, 'role': req.role}).execute()
    except Exception:
        pass
    _audit('workspace.member.role_change', 'user', user_id, actor, {'role': req.role}, workspace_id)
    return {"ok": True}

@app.delete("/api/workspaces/{workspace_id}/members/{user_id}")
def admin_remove_member(workspace_id: str, user_id: str, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    sb.table('workspace_members').delete().eq('workspace_id', workspace_id).eq('user_id', user_id).execute()
    try:
        sb.table('workspace_direct_members').delete().eq('workspace_id', workspace_id).eq('user_id', user_id).execute()
    except Exception:
        pass
    _audit('workspace.member.remove', 'user', user_id, actor, {}, workspace_id)
    return {"ok": True}

@app.delete("/api/workspaces/{workspace_id}")
def admin_delete_workspace(workspace_id: str, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    # Check if personal workspace
    ws = sb.table('workspaces').select('name, is_personal').eq('id', workspace_id).execute()
    if ws.data and (ws.data[0].get('is_personal') or str(ws.data[0].get('name')).lower().strip() == 'my workspace'):
        raise HTTPException(400, "Cannot delete personal 'My Workspace'.")
    sb.table('workspaces').delete().eq('id', workspace_id).execute()
    _audit('workspace.delete', 'workspace', workspace_id, actor, {}, workspace_id)
    return {"ok": True}


class UpdateNotificationPolicyReq(BaseModel):
    scheduler: str = "all_members"
    alert: str = "all_members"
    subscription: str = "all_members"


@app.get("/api/workspaces/{workspace_id}/notification-policy")
def admin_get_workspace_notification_policy(workspace_id: str, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    # 1. Try Services API
    try:
        url = f"{SERVICES_API_URL.rstrip('/')}/service/workspaces/{workspace_id}/notification-policy"
        resp = httpx.get(url, timeout=3.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print("Services API error fetching policy:", e)

    # 2. Fallback: Supabase direct
    try:
        sb = get_supabase()
        ws_rows = sb.table('workspaces').select('id, name, owner_id, created_by, description').eq('id', workspace_id).limit(1).execute().data or []
        if not ws_rows:
            raise HTTPException(404, "Workspace not found")
        ws = ws_rows[0]
        desc = ws.get('description') or ''
        policy = {'scheduler': 'all_members', 'alert': 'all_members', 'subscription': 'all_members'}
        if desc.startswith('{') and 'notification_policy' in desc:
            import json as _json
            p = _json.loads(desc).get('notification_policy') or {}
            policy['scheduler'] = p.get('scheduler', 'all_members')
            policy['alert'] = p.get('alert', 'all_members')
            policy['subscription'] = p.get('subscription', 'all_members')
        
        owner_id = ws.get('owner_id') or ws.get('created_by')
        owner_user = None
        if owner_id:
            u_row = sb.table('vtab_users').select('id, email, display_name').eq('id', owner_id).limit(1).execute().data or []
            if u_row:
                owner_user = u_row[0]
        return {
            "workspace_id": workspace_id,
            "workspace_name": ws.get("name", "Workspace"),
            "owner": owner_user,
            "policy": policy
        }
    except Exception as err:
        raise HTTPException(500, str(err))


@app.put("/api/workspaces/{workspace_id}/notification-policy")
@app.patch("/api/workspaces/{workspace_id}/notification-policy")
def admin_update_workspace_notification_policy(workspace_id: str, req: UpdateNotificationPolicyReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    clean_policy = {
        "scheduler": "owner_only" if req.scheduler == "owner_only" else "all_members",
        "alert": "owner_only" if req.alert == "owner_only" else "all_members",
        "subscription": "owner_only" if req.subscription == "owner_only" else "all_members",
    }
    # 1. Try Services API
    try:
        url = f"{SERVICES_API_URL.rstrip('/')}/service/workspaces/{workspace_id}/notification-policy"
        resp = httpx.put(url, json=clean_policy, timeout=3.0)
        if resp.status_code == 200:
            payload = resp.json()
            _audit('workspace.notification_policy.update', 'workspace', workspace_id, actor, clean_policy, workspace_id)
            return payload
    except Exception as e:
        print("Services API error saving policy:", e)

    # 2. Fallback: Supabase direct
    try:
        sb = get_supabase()
        ws_rows = sb.table('workspaces').select('id, name, owner_id, created_by, description').eq('id', workspace_id).limit(1).execute().data or []
        if not ws_rows:
            raise HTTPException(404, "Workspace not found")
        ws = ws_rows[0]
        existing_desc = ws.get('description') or ''
        try:
            parsed_desc = json.loads(existing_desc) if existing_desc else {}
            if not isinstance(parsed_desc, dict):
                parsed_desc = {'text': str(existing_desc)}
        except Exception:
            parsed_desc = {'text': str(existing_desc)}
        parsed_desc['notification_policy'] = clean_policy
        payload = json.dumps(parsed_desc)
        sb.table('workspaces').update({'description': payload}).eq('id', workspace_id).execute()
        _audit('workspace.notification_policy.update', 'workspace', workspace_id, actor, clean_policy, workspace_id)
        return {"ok": True, "policy": clean_policy}
    except Exception as err:
        raise HTTPException(500, str(err))


class UpdateSupportStatusReq(BaseModel):
    status: str
    notes: str | None = None

class AdminInviteReq(BaseModel):
    email: str
    role: str = "Admin"

class AdminActivateReq(BaseModel):
    email: str
    token: str

class CreateGroupReq(BaseModel):
    name: str
    description: str = ""

class GroupMembersReq(BaseModel):
    user_ids: list[str]

class GroupWorkspaceReq(BaseModel):
    workspace_id: str
    role: str = "Viewer"



@app.get("/api/support-requests")
def admin_get_support_requests(status: str | None = None, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    # 1. Try calling standalone Services API
    try:
        url = f"{SERVICES_API_URL.rstrip('/')}/service/support-requests"
        params = {}
        if status:
            params['status'] = status
        else:
            params['tab'] = 'all'
        resp = httpx.get(url, params=params, timeout=4.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print("Services API error, falling back to local database:", e)

    # 2. Fallback to local SQLite if file exists
    if os.path.exists(LOCAL_STUDIO_META):
        try:
            import sqlite3
            con = sqlite3.connect(LOCAL_STUDIO_META)
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            q = "SELECT * FROM support_requests WHERE 1=1"
            p = []
            if status:
                if status.lower() == 'open':
                    q += " AND lower(status) in ('open', 'in progress', 'pending')"
                elif status.lower() == 'closed':
                    q += " AND lower(status) in ('closed', 'resolved')"
                else:
                    q += " AND lower(status) = lower(?)"
                    p.append(status.strip())
            q += " ORDER BY created_at DESC"
            cur.execute(q, p)
            rows = [dict(r) for r in cur.fetchall()]
            con.close()
            return {"requests": rows, "total": len(rows)}
        except Exception as e:
            print("SQLite fallback error:", e)

    return {"requests": [], "total": 0}


@app.put("/api/support-requests/{request_id}/status")
@app.patch("/api/support-requests/{request_id}/status")
def admin_update_support_status(request_id: str, req: UpdateSupportStatusReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    new_status = req.status.strip()
    notes = (req.notes or "").strip()

    updated_req = None

    # 1. Try calling Services API
    try:
        url = f"{SERVICES_API_URL.rstrip('/')}/service/support-requests/{request_id}"
        resp = httpx.patch(url, json={"status": new_status, "admin_notes": notes}, timeout=4.0)
        if resp.status_code == 200:
            data = resp.json()
            updated_req = data.get("request")
    except Exception as e:
        print("Services API update error, falling back to local database:", e)

    # 2. Fallback to local SQLite if not already updated or to ensure consistency
    if os.path.exists(LOCAL_STUDIO_META):
        try:
            import sqlite3
            con = sqlite3.connect(LOCAL_STUDIO_META)
            cur = con.cursor()
            cur.execute(
                "UPDATE support_requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? OR request_number = ?",
                (new_status, request_id, request_id)
            )
            con.commit()
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM support_requests WHERE id = ? OR request_number = ?", (request_id, request_id))
            r = cur.fetchone()
            if r:
                updated_req = dict(r)
            con.close()
        except Exception as e:
            print("SQLite update error:", e)

    _audit('support.status.update', 'support_request', request_id, actor, {'status': new_status, 'notes': notes})
    if not updated_req:
        return {"ok": True, "status": new_status, "request_id": request_id}

    return {"ok": True, "request": updated_req, "status": new_status}


# ── Governance dashboard, administrators and audit ────────────────────────────

def _lookup_user_by_email(sb: Client, email: str):
    rows = sb.table('vtab_users').select('id,email,display_name').eq('email', email.lower().strip()).limit(1).execute().data or []
    return rows[0] if rows else None

@app.get("/api/governance/summary")
def governance_summary(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    def count(table: str, **filters):
        try:
            query = sb.table(table).select('*', count='exact')
            for key, value in filters.items():
                query = query.eq(key, value)
            response = query.limit(1).execute()
            return response.count if response.count is not None else len(response.data or [])
        except Exception:
            return 0
    workspaces = sb.table('workspaces').select('id,name,is_personal').execute().data or []
    team_count = len([w for w in workspaces if not w.get('is_personal') and str(w.get('name') or '').strip().lower() != 'my workspace'])
    return {
        'users': count('vtab_users'),
        'workspaces': team_count,
        'groups': count('user_groups'),
        'active_admins': count('platform_admins', status='Active'),
        'open_tickets': 0,
        'failed_refreshes': count('refresh_runs', status='failed'),
    }

@app.get("/api/admins")
def list_admins(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    rows = get_supabase().table('platform_admins').select('*').order('created_at', desc=True).execute().data or []
    for row in rows:
        if str(row.get('email') or '').lower() in SUPER_ADMIN_EMAILS:
            row['role'] = 'Super Admin'
            row['status'] = 'Active'
            row['bootstrap'] = True
    existing_emails = {str(row.get('email') or '').lower() for row in rows}
    for email in sorted(SUPER_ADMIN_EMAILS - existing_emails):
        rows.insert(0, {'email': email, 'display_name': 'Bootstrap administrator' if email == ADMIN_EMAIL else 'Vignesh Rajas', 'role': 'Super Admin', 'status': 'Active', 'bootstrap': True})
    return {'admins': rows}

@app.post("/api/admins/invitations")
def request_admin_invitation(req: AdminInviteReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    role = req.role if req.role in ('Admin', 'Auditor') else 'Admin'
    email = req.email.lower().strip()
    sb = get_supabase()
    user = _lookup_user_by_email(sb, email)
    if not user:
        raise HTTPException(400, 'Create this user account before granting administrator access.')
    token = f"{secrets.randbelow(100000000):08d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    sb.table('admin_enrollment_tokens').insert({
        'email': email,
        'role': role,
        'token_hash': hashlib.sha256(token.encode()).hexdigest(),
        'requested_by': actor.get('user_id'),
        'expires_at': expires.isoformat(),
    }).execute()
    send_brevo_email(email, 'VTAB administrator verification token', f'Your VTAB administrator verification token is: {token}\n\nIt expires in 15 minutes. Do not share it except during the approved enrollment process.')
    _audit('admin.enrollment.request', 'administrator', user['id'], actor, {'email': email, 'role': role})
    return {'ok': True, 'email': email, 'expires_at': expires.isoformat()}

@app.post("/api/admins/activate")
def activate_admin(req: AdminActivateReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    email = req.email.lower().strip()
    sb = get_supabase()
    rows = sb.table('admin_enrollment_tokens').select('*').eq('email', email).is_('consumed_at', 'null').order('created_at', desc=True).limit(1).execute().data or []
    if not rows:
        raise HTTPException(400, 'No pending administrator token was found.')
    enrollment = rows[0]
    sb.table('admin_enrollment_tokens').update({'attempts': int(enrollment.get('attempts') or 0) + 1}).eq('id', enrollment['id']).execute()
    expires_at = datetime.fromisoformat(str(enrollment['expires_at']).replace('Z', '+00:00'))
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(400, 'The administrator token has expired.')
    if int(enrollment.get('attempts') or 0) >= 5:
        raise HTTPException(429, 'Too many invalid attempts. Request a new token.')
    if not secrets.compare_digest(hashlib.sha256(req.token.strip().encode()).hexdigest(), enrollment['token_hash']):
        raise HTTPException(400, 'Invalid administrator token.')
    user = _lookup_user_by_email(sb, email)
    if not user:
        raise HTTPException(400, 'Registered user not found.')
    now = datetime.now(timezone.utc).isoformat()
    sb.table('platform_admins').upsert({
        'user_id': user['id'], 'email': email, 'display_name': user.get('display_name'),
        'role': enrollment['role'], 'status': 'Active', 'created_by': actor.get('user_id'), 'activated_at': now,
    }).execute()
    sb.table('admin_enrollment_tokens').update({'consumed_at': now}).eq('id', enrollment['id']).execute()
    _audit('admin.activate', 'administrator', user['id'], actor, {'email': email, 'role': enrollment['role']})
    return {'ok': True, 'email': email, 'role': enrollment['role']}

@app.patch("/api/admins/{user_id}/status")
def update_admin_status(user_id: str, payload: dict, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    if actor.get('user_id') == user_id:
        raise HTTPException(400, 'You cannot suspend your own administrator account.')
    status = 'Suspended' if payload.get('status') == 'Suspended' else 'Active'
    get_supabase().table('platform_admins').update({'status': status}).eq('user_id', user_id).execute()
    _audit('admin.status.update', 'administrator', user_id, actor, {'status': status})
    return {'ok': True, 'status': status}

@app.get("/api/audit")
def list_audit_events(limit: int = 300, authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    safe_limit = max(25, min(limit, 1000))
    events = []
    try:
        for row in sb.table('audit_logs').select('*').order('created_at', desc=True).limit(safe_limit).execute().data or []:
            events.append({**row, 'category': 'Governance', 'status': row.get('result', 'Success')})
    except Exception:
        pass
    try:
        for row in sb.table('published_reports').select('id,name,workspace_id,published_by,published_at,updated_at').order('updated_at', desc=True).limit(safe_limit).execute().data or []:
            events.append({'id': f"publish:{row['id']}:{row.get('updated_at')}", 'created_at': row.get('updated_at') or row.get('published_at'), 'actor_id': row.get('published_by'), 'workspace_id': row.get('workspace_id'), 'action': 'report.publish', 'object_type': 'report', 'object_id': row['id'], 'category': 'Publish', 'status': 'Success', 'details': {'name': row.get('name')}})
    except Exception:
        pass
    try:
        for row in sb.table('refresh_runs').select('*').order('created_at', desc=True).limit(safe_limit).execute().data or []:
            events.append({'id': f"refresh:{row['id']}", 'created_at': row.get('created_at'), 'actor_id': row.get('requested_by'), 'action': f"refresh.{row.get('trigger_type', 'run')}", 'object_type': 'report', 'object_id': row.get('report_id'), 'category': 'Refresh', 'status': row.get('status'), 'details': {'duration_ms': row.get('duration_ms'), 'rows_processed': row.get('rows_processed'), 'error': row.get('error_message')}})
    except Exception:
        pass
    try:
        for row in sb.table('alert_events').select('*').order('created_at', desc=True).limit(safe_limit).execute().data or []:
            events.append({'id': f"alert:{row['id']}", 'created_at': row.get('created_at'), 'action': f"alert.{row.get('event_type')}", 'object_type': 'alert_rule', 'object_id': row.get('alert_rule_id'), 'category': 'Alert', 'status': row.get('delivery_status') or row.get('event_type'), 'details': {'value': row.get('value'), 'threshold': row.get('threshold'), 'notification_id': row.get('notification_id')}})
    except Exception:
        pass
    events.sort(key=lambda row: str(row.get('created_at') or ''), reverse=True)
    return {'events': events[:safe_limit]}


# ── User groups and workspace synchronization ─────────────────────────────────

ROLE_WEIGHT = {'Viewer': 1, 'Contributor': 2, 'Member': 3, 'Admin': 4}

def _effective_workspace_role(sb: Client, workspace_id: str, user_id: str):
    roles = []
    direct = sb.table('workspace_direct_members').select('role').eq('workspace_id', workspace_id).eq('user_id', user_id).execute().data or []
    roles.extend(row['role'] for row in direct)
    links = sb.table('workspace_group_member_links').select('role').eq('workspace_id', workspace_id).eq('user_id', user_id).execute().data or []
    roles.extend(row['role'] for row in links)
    return max(roles, key=lambda role: ROLE_WEIGHT.get(role, 0)) if roles else None

def _apply_effective_membership(sb: Client, workspace_id: str, user_id: str):
    role = _effective_workspace_role(sb, workspace_id, user_id)
    if role:
        sb.table('workspace_members').upsert({'workspace_id': workspace_id, 'user_id': user_id, 'role': role}).execute()
    else:
        workspace = sb.table('workspaces').select('created_by').eq('id', workspace_id).limit(1).execute().data or []
        if not workspace or str(workspace[0].get('created_by')) != str(user_id):
            sb.table('workspace_members').delete().eq('workspace_id', workspace_id).eq('user_id', user_id).execute()

@app.get("/api/groups")
def list_groups(authorization: str | None = Header(default=None)):
    _require_admin(authorization)
    sb = get_supabase()
    groups = sb.table('user_groups').select('*').order('name').execute().data or []
    members = sb.table('user_group_members').select('group_id,user_id').execute().data or []
    grants = sb.table('workspace_group_grants').select('group_id,workspace_id,role').execute().data or []
    for group in groups:
        group['member_ids'] = [row['user_id'] for row in members if row['group_id'] == group['id']]
        group['workspace_grants'] = [row for row in grants if row['group_id'] == group['id']]
        group['member_count'] = len(group['member_ids'])
        group['workspace_count'] = len(group['workspace_grants'])
    return {'groups': groups}

@app.post("/api/groups")
def create_group(req: CreateGroupReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    name = req.name.strip()
    if not name:
        raise HTTPException(400, 'Group name is required.')
    row = get_supabase().table('user_groups').insert({'name': name, 'description': req.description.strip(), 'created_by': actor.get('user_id')}).execute().data[0]
    _audit('group.create', 'user_group', row['id'], actor, {'name': name})
    return {'ok': True, 'group': row}

@app.delete("/api/groups/{group_id}")
def delete_group(group_id: str, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    links = sb.table('workspace_group_member_links').select('workspace_id,user_id').eq('group_id', group_id).execute().data or []
    sb.table('user_groups').delete().eq('id', group_id).execute()
    for link in links:
        _apply_effective_membership(sb, link['workspace_id'], link['user_id'])
    _audit('group.delete', 'user_group', group_id, actor)
    return {'ok': True}

@app.post("/api/groups/{group_id}/members")
def add_group_members(group_id: str, req: GroupMembersReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    grants = sb.table('workspace_group_grants').select('workspace_id,role').eq('group_id', group_id).execute().data or []
    for user_id in set(req.user_ids):
        sb.table('user_group_members').upsert({'group_id': group_id, 'user_id': user_id, 'added_by': actor.get('user_id')}).execute()
        for grant in grants:
            sb.table('workspace_group_member_links').upsert({'workspace_id': grant['workspace_id'], 'group_id': group_id, 'user_id': user_id, 'role': grant['role']}).execute()
            _apply_effective_membership(sb, grant['workspace_id'], user_id)
    _audit('group.members.add', 'user_group', group_id, actor, {'user_ids': list(set(req.user_ids))})
    return {'ok': True}

@app.delete("/api/groups/{group_id}/members/{user_id}")
def remove_group_member(group_id: str, user_id: str, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    links = sb.table('workspace_group_member_links').select('workspace_id').eq('group_id', group_id).eq('user_id', user_id).execute().data or []
    sb.table('user_group_members').delete().eq('group_id', group_id).eq('user_id', user_id).execute()
    sb.table('workspace_group_member_links').delete().eq('group_id', group_id).eq('user_id', user_id).execute()
    for link in links:
        _apply_effective_membership(sb, link['workspace_id'], user_id)
    _audit('group.member.remove', 'user_group', group_id, actor, {'user_id': user_id})
    return {'ok': True}

@app.post("/api/groups/{group_id}/workspaces")
def assign_group_workspace(group_id: str, req: GroupWorkspaceReq, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    role = req.role if req.role in ROLE_WEIGHT else 'Viewer'
    sb = get_supabase()
    sb.table('workspace_group_grants').upsert({'workspace_id': req.workspace_id, 'group_id': group_id, 'role': role, 'granted_by': actor.get('user_id')}).execute()
    members = sb.table('user_group_members').select('user_id').eq('group_id', group_id).execute().data or []
    for member in members:
        sb.table('workspace_group_member_links').upsert({'workspace_id': req.workspace_id, 'group_id': group_id, 'user_id': member['user_id'], 'role': role}).execute()
        _apply_effective_membership(sb, req.workspace_id, member['user_id'])
    _audit('workspace.group.assign', 'user_group', group_id, actor, {'role': role}, req.workspace_id)
    return {'ok': True}

@app.delete("/api/groups/{group_id}/workspaces/{workspace_id}")
def remove_group_workspace(group_id: str, workspace_id: str, authorization: str | None = Header(default=None)):
    actor = _require_admin(authorization, write=True)
    sb = get_supabase()
    links = sb.table('workspace_group_member_links').select('user_id').eq('group_id', group_id).eq('workspace_id', workspace_id).execute().data or []
    sb.table('workspace_group_grants').delete().eq('group_id', group_id).eq('workspace_id', workspace_id).execute()
    sb.table('workspace_group_member_links').delete().eq('group_id', group_id).eq('workspace_id', workspace_id).execute()
    for link in links:
        _apply_effective_membership(sb, workspace_id, link['user_id'])
    _audit('workspace.group.remove', 'user_group', group_id, actor, {}, workspace_id)
    return {'ok': True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)



