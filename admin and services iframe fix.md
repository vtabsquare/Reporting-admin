# VTAB Reporting Services & Admin Console: Iframe Embed & UI Permission Enforcement Fix

> **Target Version**: VTAB Reporting Services v6.1.16+ / VTAB Admin Console v2.2+  
> **Purpose**: Technical specification and implementation guide for Codex / automated agent to enforce `vtabpublicuser@gmail.com` permissions in all iframe embeds and fix workspace member permission resolution without impacting deployment or authoring features.

---

## 1. Executive Summary & Goals

1. **Dedicated Iframe Identity**:
   - Every iframe embed (`?embed=1&report=<id>` or `?public=1&report=<id>`) must run under the designated public account: **`vtabpublicuser@gmail.com`**.
   - The report viewer must dynamically fetch and strictly enforce the UI permissions configured for `vtabpublicuser@gmail.com` in that report's workspace from the Admin Console.
   - Example: If the **View ribbon** switch is turned **OFF** for `vtabpublicuser@gmail.com` in that workspace, the View tab is disabled/hidden in the iframe. If the **Home ribbon** switch is turned **ON**, the Home ribbon is fully active and clickable in the iframe.
2. **Workspace Member Permission Resolution (Harish Fix)**:
   - In the normal workspace portal (`?workspace=1`), only the true **Workspace Owner** unconditionally retains all commands (`DEFAULT_REPORT_UI_PERMISSIONS`).
   - Members with other roles (including **Admin**, **Member**, **Contributor**, and **Viewer**) must have their permissions resolved from `description.member_ui_permissions` in the workspace row.
   - This fixes the bug where an Admin (e.g. Harish) saw all commands enabled even after every switch was toggled OFF in the Admin Console.
3. **Zero Regression Guarantee**:
   - Must **not** alter or break any existing functionality.
   - Specifically preserves all **Manager Application Deployment** endpoints (`/api/v1/update/*`, webhooks, updater daemon).
   - Preserves Supabase RLS policies, desktop authoring, DuckDB columnar engine, transform pipelines, and semantic models.

---

## 2. File Change Specifications

### A. `Reporting Tool Services/src/services.tsx`

#### Objective:
1. Allow unauthenticated public viewers to view embedded reports without being blocked by `SupabaseAuthGate`.
2. Hardcode `vtabpublicuser@gmail.com` as the viewer identity for embed mode.

#### Code Diff / Replacement:
```tsx
// Locate the render logic in Services():
if (!ready) return <div className="loading"><div className="brandMark">V</div><span>Loading workspace…</span></div>;

// ── Embed / iframe check runs BEFORE the session gate ───────────────────────
// Always uses vtabpublicuser@gmail.com so the Admin Console UI-permission
// settings for that account are enforced in every embedded report view.
// Non-embed (direct portal) flow is completely unaffected.
if (isEmbed && embedReportId) {
  const EMBED_VIEWER_EMAIL = 'vtabpublicuser@gmail.com';
  return (
    <div className="pbi-app-shell" style={{width:'100vw',height:'100vh',overflow:'hidden',display:'flex',flexDirection:'column'}}>
      <PublishedViewer 
        reportId={embedReportId} 
        embedded={true} 
        cloudMode={true} 
        userRole="Viewer"
        currentUserEmail={EMBED_VIEWER_EMAIL}
      />
    </div>
  );
}

if (!session) return <SupabaseAuthGate onSignedIn={setSession}/>;
return <CloudWorkspace session={session}/>;
```

---

### B. `Reporting Tool Services/api/app/server.py`

#### Objective:
Provide a public API endpoint to resolve the UI permissions for `vtabpublicuser@gmail.com` for a given published report without requiring a user Bearer token.

#### Location:
Add right after `_enforce_viewer_block` and before `_enforce_report_ui_permission` (around line 379).

#### Code to Add:
```python
# ── Embed-permissions endpoint ────────────────────────────────────────────────
# The designated public viewer account whose Admin Console UI-permission
# settings are enforced for every iframe-embedded report view.
_EMBED_VIEWER_EMAIL = 'vtabpublicuser@gmail.com'

# Permission keys and their defaults (all enabled by default).
_EMBED_PERMISSION_DEFAULTS: dict = {
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

# Alias map: canonical key -> legacy keys that may appear in older workspace data
_EMBED_PERMISSION_ALIASES: dict = {
    'can_file':      ('file_menu', 'file_ribbon'),
    'can_home':      ('home_ribbon',),
    'can_view':      ('view_ribbon',),
    'can_share':     ('share',),
    'can_pdf':       ('pdf',),
    'can_ppt':       ('ppt', 'powerpoint'),
    'can_refresh':   ('refresh',),
    'can_subscribe': ('subscribe',),
    'can_alert':     ('alerts', 'alert'),
    'can_download':  ('download_project', 'download'),
}

@app.get('/api/v1/published/{report_id}/embed-permissions')
def published_embed_permissions(report_id: str):
    """Return UI-permission settings for the public embed viewer account.

    Uses the service-role key internally so no user Bearer token is needed.
    This lets unauthenticated iframe viewers (Edge, Chrome, Safari) inherit
    exactly the permissions configured in the Admin Console for
    vtabpublicuser@gmail.com in the report's workspace.

    Non-embed (direct portal) flows never call this endpoint and are
    completely unaffected by this implementation.
    """
    defaults = {**_EMBED_PERMISSION_DEFAULTS}
    try:
        from .supabase_store import _admin_client
        sb = _admin_client()

        # 1. Look up the embed account's vtab_users row by email (case-insensitive).
        user_rows = (
            sb.table('vtab_users')
            .select('id')
            .ilike('email', _EMBED_VIEWER_EMAIL)
            .limit(1)
            .execute()
            .data or []
        )
        embed_user_id = str(user_rows[0].get('id') or '') if user_rows else ''

        # 2. Find the report and its workspace.
        report_rows = (
            sb.table('published_reports')
            .select('workspace_id,owner_id')
            .eq('id', report_id)
            .limit(1)
            .execute()
            .data or []
        )
        if not report_rows:
            return defaults

        workspace_id = report_rows[0].get('workspace_id')
        if not workspace_id:
            return defaults

        # 3. Read workspace description -> member_ui_permissions.
        ws_rows = (
            sb.table('workspaces')
            .select('description')
            .eq('id', workspace_id)
            .limit(1)
            .execute()
            .data or []
        )
        if not ws_rows:
            return defaults

        try:
            description = json.loads(ws_rows[0].get('description') or '{}')
        except Exception:
            description = {}

        permission_map = description.get('member_ui_permissions') or {}
        configured: dict = {}
        if embed_user_id and isinstance(permission_map.get(embed_user_id), dict):
            configured = permission_map[embed_user_id]
        elif isinstance(permission_map.get(_EMBED_VIEWER_EMAIL.lower()), dict):
            configured = permission_map[_EMBED_VIEWER_EMAIL.lower()]

        # 4. Resolve legacy aliases so older workspace data still works.
        normalized = dict(configured)
        for canonical, legacy_keys in _EMBED_PERMISSION_ALIASES.items():
            if canonical not in normalized:
                for lk in legacy_keys:
                    if lk in normalized:
                        normalized[canonical] = normalized[lk]
                        break

        # 5. Build result: start from defaults, overlay configured values.
        resolved = {k: bool(normalized.get(k, v)) for k, v in _EMBED_PERMISSION_DEFAULTS.items()}
        # If all_commands is explicitly False, collapse every permission to False.
        if resolved.get('all_commands') is False:
            resolved = {k: False for k in _EMBED_PERMISSION_DEFAULTS}
        else:
            resolved['all_commands'] = all(resolved[k] for k in resolved if k != 'all_commands')
        return resolved

    except Exception as exc:
        logger.warning('embed-permissions lookup failed for %s: %s', report_id, exc)
        return defaults
```

*Note: The authoring security middleware already whitelists paths starting with `/api/v1/published`, so `/api/v1/published/{report_id}/embed-permissions` requires no special middleware bypass.*

---

### C. `Reporting Tool Services/src/uiPermissions.ts`

#### Objective:
Support matching by either Supabase `user_id` (UUID) or lowercase `email` when reading `member_ui_permissions`.

#### Replacement:
```ts
export type ReportUiPermissions = {
  all_commands: boolean;
  can_file: boolean;
  can_home: boolean;
  can_view: boolean;
  can_share: boolean;
  can_pdf: boolean;
  can_ppt: boolean;
  can_refresh: boolean;
  can_subscribe: boolean;
  can_alert: boolean;
  can_download: boolean;
};

export const DEFAULT_REPORT_UI_PERMISSIONS: ReportUiPermissions = {
  all_commands: true,
  can_file: true,
  can_home: true,
  can_view: true,
  can_share: true,
  can_pdf: true,
  can_ppt: true,
  can_refresh: true,
  can_subscribe: true,
  can_alert: true,
  can_download: true,
};

export function resolveReportUiPermissions(
  description: unknown,
  userId?: string,
  userEmail?: string
): ReportUiPermissions {
  if (!userId && !userEmail) return { ...DEFAULT_REPORT_UI_PERMISSIONS };
  try {
    const parsed = typeof description === 'string' ? JSON.parse(description) : description;
    const map = (parsed as any)?.member_ui_permissions || {};
    const configured =
      (userId && map[userId]) ||
      (userEmail && map[userEmail.toLowerCase()]) ||
      {};
    const merged = { ...DEFAULT_REPORT_UI_PERMISSIONS, ...configured };
    if (merged.all_commands === false) {
      return Object.fromEntries(
        Object.keys(DEFAULT_REPORT_UI_PERMISSIONS).map(key => [key, false])
      ) as ReportUiPermissions;
    }
    return merged;
  } catch {
    return { ...DEFAULT_REPORT_UI_PERMISSIONS };
  }
}
```

---

### D. `Reporting Tool Services/src/v11/CloudWorkspace.tsx`

#### Objective:
1. Fix Harish's permission leak: Ensure only the **Workspace Owner** retains all commands unconditionally.
2. Ensure Admins, Members, Contributors, and Viewers have their permissions resolved via `resolveReportUiPermissions` using both `user_id` and `user_email`.

#### Code Changes:
1. **Ensure Import**:
   ```tsx
   import { resolveReportUiPermissions, DEFAULT_REPORT_UI_PERMISSIONS } from '../uiPermissions';
   ```
2. **Viewer Mode Permission Resolution** (around line 378):
   ```tsx
   // ─── VIEWER MODE ─────────────────────────────────────────────────────────────
   if (viewing) {
     // Only the workspace Owner retains all commands unconditionally ("Workspace owners always retain every command").
     // Admins, Members, Contributors, and Viewers have their permissions resolved
     // from member_ui_permissions configured in the Admin Console.
     const isOwner =
       activeWorkspace?.role === 'Owner' ||
       (activeWorkspace as any)?.owner_id === session?.user?.id ||
       (activeWorkspace as any)?.created_by === session?.user?.id;

     const userUiPermissions = isOwner
       ? { ...DEFAULT_REPORT_UI_PERMISSIONS }
       : resolveReportUiPermissions(
           (activeWorkspace as any)?.description,
           session?.user?.id,
           session?.user?.email
         );

     return (
       <div className="pbi-app-shell">
         <ServicesUpdateExperience />
         <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
           <PublishedViewer 
             reportId={viewing.id} 
             userRole={viewing.role} 
             initialItem={{ id: viewing.id, name: viewing.name, published_at: viewing.published_at, updated_at: viewing.updated_at || viewing.published_at, project: viewing.project, role: viewing.role, workspace_id: viewing.workspace_id || activeWorkspace?.id }} 
             embedded 
             cloudMode 
             initialPaginatedId={viewing.paginatedId}
             workspacePermissions={userUiPermissions}
             onBack={() => { setViewing(null); setSharing(null); history.replaceState(null, '', location.pathname + '?workspace=1'); }}
             onManageAccess={userUiPermissions.can_share && (viewing.role === "Co-Owner" || viewing.role === "Owner" || viewing.role === "Admin") && !isPersonalReport(viewing) ? () => setSharing(viewing) : undefined}
           />
         </div>
       ...
   ```

---

### E. `Reporting Tool Services/src/v11/PublishedViewer.tsx`

#### Objective:
1. Fix `.single()` -> `.maybeSingle()` to prevent PGRST116 crashes in Edge/Safari.
2. Disentangle `isExternalEmbed` from the internal `embedded` prop.
3. Fetch embed permissions for `vtabpublicuser@gmail.com` when in an iframe embed.
4. Remove hardcoded `embedFade` / `disabled={isEmbedContext}` blanket blocks so ribbon buttons obey permissions cleanly.
5. Hide the Back button when embedded in an external iframe.

#### Code Changes:

##### 1. Supabase Query Fix (Line 34-45):
```tsx
async function fetchReportFromSupabase(reportId:string):Promise<any>{
  const{supabase}=await import('../supabase');
  if(!supabase)throw new Error('Supabase not configured');
  
  const{data,error}=await supabase
    .from('published_reports')
    .select('id,name,published_at,updated_at,project_json,workspace_id')
    .eq('id',reportId)
    .maybeSingle();

  if(error)throw error;
  if(!data)throw new Error('Published report not found or access denied.');

  return{...data,project:parseProjectJson(data.project_json)};
}
```

##### 2. Embed Detection & Permission Fetching (Around Line 388):
```tsx
export default function PublishedViewer({reportId,initialItem,embedded=false,cloudMode=false,initialPaginatedId,userRole,onBack,onManageAccess,workspacePermissions,currentUserEmail="vtabdemouser@gmail.com"}:{reportId:string,initialItem?:any,embedded?:boolean,cloudMode?:boolean,initialPaginatedId?:string,userRole?:string,onBack?:()=>void,onManageAccess?:()=>void,workspacePermissions?:Partial<ReportUiPermissions>,currentUserEmail?:string}){
  // Detect external iframe/embed context strictly from URL parameters.
  // The internal `embedded` prop is passed by CloudWorkspace to indicate the viewer is
  // rendered inside the workspace shell. That is NOT an external iframe embed and must
  // NEVER trigger embed restrictions or public user permission fetching.
  const isExternalEmbed = typeof window !== 'undefined' &&
    (new URLSearchParams(window.location.search).get('embed') === '1' ||
     new URLSearchParams(window.location.search).get('public') === '1');
  const isEmbedContext = isExternalEmbed;
  const embedFade = {};

  const[item,setItem]=useState<any>((initialItem && initialItem.project)?initialItem:null)...
  const[activeRibbonTab,setActiveRibbonTab]=useState<'Home'|'File'|'View'>('Home');

  // ── Embed permission enforcement ────────────────────────────────────────────
  // When this viewer is loaded in an external iframe (embed=1 or public=1),
  // fetch UI permissions configured in Admin Console for vtabpublicuser@gmail.com.
  // Inside the workspace, workspacePermissions (logged-in user) is used directly.
  const[embedPermissions,setEmbedPermissions]=useState<Partial<ReportUiPermissions>|null>(null);
  useEffect(()=>{
   if(!isExternalEmbed)return;
   let cancelled=false;
   api<Partial<ReportUiPermissions>>(`/published/${reportId}/embed-permissions`)
    .then(value=>{if(!cancelled)setEmbedPermissions(value)})
    .catch(()=>{if(!cancelled)setEmbedPermissions({})});
   return()=>{cancelled=true};
  },[reportId,isExternalEmbed]);

  const effectivePermissions = isExternalEmbed ? (embedPermissions ?? {}) : (workspacePermissions ?? {});
  const permissions=useMemo(()=>({...DEFAULT_REPORT_UI_PERMISSIONS,...effectivePermissions}),[effectivePermissions]);
  const allowed=(key:keyof ReportUiPermissions)=>permissions.all_commands!==false&&permissions[key]!==false;

  // Auto-switch ribbon tab if the active tab is disabled by policy
  useEffect(() => {
    if (activeRibbonTab === 'Home' && !allowed('can_home')) {
      if (allowed('can_view')) setActiveRibbonTab('View');
    } else if (activeRibbonTab === 'View' && !allowed('can_view')) {
      if (allowed('can_home')) setActiveRibbonTab('Home');
    }
  }, [permissions]);
```

##### 3. Ribbon Bar Buttons Clean-up:
- **Back Button**:
  ```tsx
  {(onBack && !isExternalEmbed) && (
    <button onClick={onBack} className="pbi-btn-back" title="Back to workspace">
      <ArrowLeft size={14} /> Back
    </button>
  )}
  ```
- **Share Button**:
  ```tsx
  <button 
    disabled={!allowed('can_share')} 
    onClick={onManageAccess || shareEmail} 
    style={{ display: 'flex', alignItems: 'center', gap: 6, background: '#0d6257', color: '#fff', border: 'none', borderRadius: 4, padding: '6px 14px', fontWeight: 600, fontSize: 12, cursor: allowed('can_share') ? 'pointer' : 'not-allowed', opacity: allowed('can_share') ? 1 : 0.42 }}
  >
    <Share2 size={14} /> Share
  </button>
  ```
- **File Tab**:
  ```tsx
  <button 
    className={`pbi-ribbon-tab-btn ${fileDropdownOpen ? 'active' : ''}`}
    disabled={!allowed('can_file')}
    onClick={() => allowed('can_file') && setFileDropdownOpen(!fileDropdownOpen)}
    title={!allowed('can_file') ? "File menu is disabled" : undefined}
  >
    File <ChevronDown size={12} style={{ marginLeft: 2 }} />
  </button>
  ```
- **Home & View Tabs**:
  ```tsx
  <button 
    className={`pbi-ribbon-tab-btn ${activeRibbonTab === 'Home' ? 'active' : ''}`}
    disabled={!allowed('can_home')}
    onClick={() => { setActiveRibbonTab('Home'); setFileDropdownOpen(false); }}
  >
    Home
  </button>
  <button 
    className={`pbi-ribbon-tab-btn ${activeRibbonTab === 'View' ? 'active' : ''}`}
    disabled={!allowed('can_view')}
    onClick={() => { setActiveRibbonTab('View'); setFileDropdownOpen(false); }}
  >
    View
  </button>
  ```
- **Home Command Buttons** (PDF, PPT, Refresh, Subscribe, Alert):
  Remove `isEmbedContext` disables. Keep standard `allowed()` checks:
  ```tsx
  <button className="pbi-cmd-btn" onClick={() => exportFile('pdf')} disabled={!!exporting || !allowed('can_pdf')}>
    <FileDown size={15} color="#dc2626" /> PDF
  </button>
  <button className="pbi-cmd-btn" disabled={!allowed('can_refresh')} onClick={load}>
    <RefreshCcw size={15} color="#16a34a" /> Refresh
  </button>
  ```
- **Admin Portal Link**:
  ```tsx
  <a
    href="https://admin-reporting.vtabsquare.com"
    target="_blank"
    rel="noopener noreferrer"
    className="pbi-cmd-btn"
    aria-disabled={!allowed('can_home')}
    tabIndex={allowed('can_home') ? 0 : -1}
    onClick={event => { if (!allowed('can_home')) event.preventDefault(); }}
    title={allowed('can_home') ? "Open Admin Portal in new tab" : "Admin portal is disabled"}
    style={{
      textDecoration: 'none',
      pointerEvents: allowed('can_home') ? 'auto' : 'none',
      opacity: allowed('can_home') ? 1 : 0.45,
      cursor: allowed('can_home') ? 'pointer' : 'not-allowed',
      background: '#f0f7fc',
      border: '1px solid #cce4f7',
      color: '#0f6cbd',
      fontWeight: 600,
      borderRadius: 4,
      padding: '0 10px',
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
    }}
  >
  ```

---

## 3. Preserved Functionalities & Architecture Safeguards

| Feature / Subsystem | Status | Verification & Reason |
| :--- | :--- | :--- |
| **Manager App Deployment (`/api/v1/update/*`)** | ✅ **100% Intact** | Zero lines modified in `update_service.py` or updater endpoints. Auto-update poller (`ServicesUpdateExperience.tsx`), check/pull commands, and webhook routes are completely untouched. |
| **Supabase Authentication & Gate** | ✅ **100% Intact** | `SupabaseAuthGate.tsx` and session restoration listeners in `services.tsx` remain active for all direct portal visits (`/?workspace=1`). |
| **Workspace Portal Role-Based Access** | ✅ **100% Intact** | Owners retain all permissions. Non-owners correctly inherit workspace-specific `member_ui_permissions`. |
| **Edge / Safari Compatibility** | ✅ **Enhanced** | `.maybeSingle()` prevents `PGRST116` null-coercion errors when loading published reports across different browsers. |
| **Reporting Engines (DuckDB, DAX, Transform)** | ✅ **100% Intact** | No alterations to analytical engines, semantic batch queries, or export generators. |

---

## 4. Build & Deployment Commands

To build and run locally after applying the edits:

```powershell
# 1. Reporting Services Frontend Build
cd "Reporting Tool Services"
npm run build

# 2. Run Reporting Services Web & API
python run_web_tool.py

# 3. In a separate terminal, run Admin Console
cd "VTAB-Admin-Console"
python run_admin_app.py
```

### Verification Checklist:
1. **Admin Console**: Navigate to workspace members, toggle switches for `vtabpublicuser@gmail.com` and non-owner members (e.g. Harish).
2. **Iframe Embed**: Open `http://127.0.0.1:4173/?embed=1&report=<report_id>`. Verify buttons mirror the settings for `vtabpublicuser@gmail.com`.
3. **Owner Portal**: Log in as Owner at `http://127.0.0.1:4173/?workspace=1`. Verify all commands and the Back button are available.
4. **Member Portal**: Log in as a member (e.g. Harish). Verify disabled commands are properly greyed out.
