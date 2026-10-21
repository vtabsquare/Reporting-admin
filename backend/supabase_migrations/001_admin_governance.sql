-- VTAB Admin Console governance foundation
-- Run once in Supabase SQL Editor after the Reporting Services migrations.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.platform_admins (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  email text NOT NULL UNIQUE,
  display_name text,
  role text NOT NULL DEFAULT 'Admin' CHECK (role IN ('Super Admin','Admin','Auditor')),
  status text NOT NULL DEFAULT 'Active' CHECK (status IN ('Pending','Active','Suspended')),
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  last_login_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.admin_enrollment_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  role text NOT NULL CHECK (role IN ('Admin','Auditor')),
  token_hash text NOT NULL,
  requested_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  attempts integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_groups (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  description text NOT NULL DEFAULT '',
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_group_members (
  group_id uuid NOT NULL REFERENCES public.user_groups(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  added_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  added_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (group_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.workspace_group_grants (
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  group_id uuid NOT NULL REFERENCES public.user_groups(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('Admin','Member','Contributor','Viewer')),
  granted_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  granted_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, group_id)
);

-- Tracks memberships materialized from groups so removal never revokes a
-- separately assigned direct membership.
CREATE TABLE IF NOT EXISTS public.workspace_group_member_links (
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  group_id uuid NOT NULL REFERENCES public.user_groups(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('Admin','Member','Contributor','Viewer')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, group_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.workspace_direct_members (
  workspace_id uuid NOT NULL REFERENCES public.workspaces(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role text NOT NULL CHECK (role IN ('Admin','Member','Contributor','Viewer')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace_id, user_id)
);

-- Existing memberships are direct until explicitly managed as group-derived.
INSERT INTO public.workspace_direct_members(workspace_id,user_id,role)
SELECT workspace_id,user_id,role FROM public.workspace_members
ON CONFLICT (workspace_id,user_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_admin_enrollment_email ON public.admin_enrollment_tokens(lower(email), expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_group_members_user ON public.user_group_members(user_id, group_id);
CREATE INDEX IF NOT EXISTS idx_workspace_group_links_user ON public.workspace_group_member_links(user_id, workspace_id);

ALTER TABLE public.platform_admins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_enrollment_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_group_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_group_member_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.workspace_direct_members ENABLE ROW LEVEL SECURITY;

-- The Admin backend uses service_role. Authenticated users only need group names
-- for future Services sharing selectors; membership lists remain private.
DROP POLICY IF EXISTS "Authenticated users see group names" ON public.user_groups;
CREATE POLICY "Authenticated users see group names" ON public.user_groups
FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "Service role manages platform admins" ON public.platform_admins;
CREATE POLICY "Service role manages platform admins" ON public.platform_admins FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages admin enrollment" ON public.admin_enrollment_tokens;
CREATE POLICY "Service role manages admin enrollment" ON public.admin_enrollment_tokens FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages user groups" ON public.user_groups;
CREATE POLICY "Service role manages user groups" ON public.user_groups FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages group members" ON public.user_group_members;
CREATE POLICY "Service role manages group members" ON public.user_group_members FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages workspace group grants" ON public.workspace_group_grants;
CREATE POLICY "Service role manages workspace group grants" ON public.workspace_group_grants FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages workspace group links" ON public.workspace_group_member_links;
CREATE POLICY "Service role manages workspace group links" ON public.workspace_group_member_links FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS "Service role manages direct workspace members" ON public.workspace_direct_members;
CREATE POLICY "Service role manages direct workspace members" ON public.workspace_direct_members FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Bootstrap the configured first administrator manually after replacing the
-- placeholders, or let the backend bootstrap ADMIN_EMAIL on its first login.
-- INSERT INTO public.platform_admins(user_id,email,display_name,role,status,activated_at)
-- SELECT id,email,'Initial administrator','Super Admin','Active',now()
-- FROM auth.users WHERE lower(email)=lower('admin@example.com')
-- ON CONFLICT (user_id) DO NOTHING;
