-- Club system schema
-- Run after 004_hand_history_room_sessions.sql
-- Adds clubs, memberships, invites, bans, rulesets, club tables, and audit logs.

-- ═══════════════════════════════════════════════════════════════
-- 1) clubs
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.clubs (
  id uuid primary key default gen_random_uuid(),
  code varchar(8) not null,
  name varchar(80) not null,
  description text not null default '',
  owner_user_id uuid not null references auth.users(id) on delete cascade,
  visibility varchar(16) not null default 'private' check (visibility in ('private', 'unlisted')),
  default_ruleset_id uuid, -- FK added after club_rulesets exists
  is_archived boolean not null default false,
  require_approval_to_join boolean not null default true,
  badge_color varchar(7),   -- hex color e.g. #FF5733
  logo_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists idx_clubs_code_unique on public.clubs(code);
create index if not exists idx_clubs_owner on public.clubs(owner_user_id);

-- ═══════════════════════════════════════════════════════════════
-- 2) club_members
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_members (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role varchar(16) not null default 'member' check (role in ('owner', 'admin', 'host', 'mod', 'member')),
  status varchar(16) not null default 'active' check (status in ('active', 'pending', 'banned', 'left')),
  nickname_in_club varchar(32),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  primary key (club_id, user_id)
);

create index if not exists idx_club_members_user on public.club_members(user_id);
create index if not exists idx_club_members_status on public.club_members(club_id, status);

-- ═══════════════════════════════════════════════════════════════
-- 3) club_invites
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_invites (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  invite_code varchar(16) not null,
  created_by uuid not null references auth.users(id) on delete cascade,
  expires_at timestamptz,
  max_uses integer,
  uses_count integer not null default 0,
  revoked boolean not null default false,
  created_at timestamptz not null default now()
);

create unique index if not exists idx_club_invites_code on public.club_invites(invite_code);
create index if not exists idx_club_invites_club on public.club_invites(club_id);

-- ═══════════════════════════════════════════════════════════════
-- 4) club_bans
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_bans (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  reason text not null default '',
  banned_by uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz  -- null = permanent
);

create index if not exists idx_club_bans_club_user on public.club_bans(club_id, user_id);

-- ═══════════════════════════════════════════════════════════════
-- 5) club_rulesets
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_rulesets (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  name varchar(80) not null,
  rules_json jsonb not null default '{}'::jsonb,
  created_by uuid not null references auth.users(id) on delete cascade,
  is_default boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_club_rulesets_club on public.club_rulesets(club_id);

-- Now add FK from clubs.default_ruleset_id -> club_rulesets.id
alter table public.clubs
  add constraint fk_clubs_default_ruleset
  foreign key (default_ruleset_id) references public.club_rulesets(id) on delete set null;

-- ═══════════════════════════════════════════════════════════════
-- 6) club_tables
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_tables (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  room_code varchar(12),
  name varchar(80) not null default 'Club Table',
  ruleset_id uuid references public.club_rulesets(id) on delete set null,
  status varchar(16) not null default 'open' check (status in ('open', 'paused', 'closed')),
  created_by uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);

create index if not exists idx_club_tables_club on public.club_tables(club_id, status);
create unique index if not exists idx_club_tables_room_code on public.club_tables(room_code) where room_code is not null;

-- ═══════════════════════════════════════════════════════════════
-- 7) club_audit_log
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_audit_log (
  id bigint generated always as identity primary key,
  club_id uuid not null references public.clubs(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,
  action_type varchar(40) not null,
  payload_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_club_audit_log_club_time on public.club_audit_log(club_id, created_at desc);

-- ═══════════════════════════════════════════════════════════════
-- RLS
-- ═══════════════════════════════════════════════════════════════

alter table public.clubs enable row level security;
alter table public.club_members enable row level security;
alter table public.club_invites enable row level security;
alter table public.club_bans enable row level security;
alter table public.club_rulesets enable row level security;
alter table public.club_tables enable row level security;
alter table public.club_audit_log enable row level security;

-- Helper: is the current user an active member of the club?
create or replace function public.is_club_member(p_club_id uuid)
returns boolean
language sql stable security definer
as $$
  select exists (
    select 1 from public.club_members
    where club_id = p_club_id
      and user_id = auth.uid()
      and status = 'active'
  );
$$;

-- Helper: does the current user have an admin-level role?
create or replace function public.is_club_admin(p_club_id uuid)
returns boolean
language sql stable security definer
as $$
  select exists (
    select 1 from public.club_members
    where club_id = p_club_id
      and user_id = auth.uid()
      and status = 'active'
      and role in ('owner', 'admin')
  );
$$;

-- Helper: is the current user a mod or above?
create or replace function public.is_club_mod(p_club_id uuid)
returns boolean
language sql stable security definer
as $$
  select exists (
    select 1 from public.club_members
    where club_id = p_club_id
      and user_id = auth.uid()
      and status = 'active'
      and role in ('owner', 'admin', 'mod')
  );
$$;

-- ── clubs ──
-- Members can read their clubs; anyone can read unlisted clubs (for join-by-code)
drop policy if exists clubs_select on public.clubs;
create policy clubs_select on public.clubs
  for select to authenticated
  using (
    visibility = 'unlisted'
    or owner_user_id = auth.uid()
    or public.is_club_member(id)
  );

-- Service role writes
drop policy if exists clubs_service_role_all on public.clubs;
create policy clubs_service_role_all on public.clubs
  for all to service_role
  using (true)
  with check (true);

-- ── club_members ──
drop policy if exists club_members_select on public.club_members;
create policy club_members_select on public.club_members
  for select to authenticated
  using (
    user_id = auth.uid()
    or public.is_club_member(club_id)
  );

drop policy if exists club_members_service_role_all on public.club_members;
create policy club_members_service_role_all on public.club_members
  for all to service_role
  using (true)
  with check (true);

-- ── club_invites ──
drop policy if exists club_invites_select on public.club_invites;
create policy club_invites_select on public.club_invites
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_invites_service_role_all on public.club_invites;
create policy club_invites_service_role_all on public.club_invites
  for all to service_role
  using (true)
  with check (true);

-- ── club_bans ──
drop policy if exists club_bans_select on public.club_bans;
create policy club_bans_select on public.club_bans
  for select to authenticated
  using (public.is_club_mod(club_id));

drop policy if exists club_bans_service_role_all on public.club_bans;
create policy club_bans_service_role_all on public.club_bans
  for all to service_role
  using (true)
  with check (true);

-- ── club_rulesets ──
drop policy if exists club_rulesets_select on public.club_rulesets;
create policy club_rulesets_select on public.club_rulesets
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_rulesets_service_role_all on public.club_rulesets;
create policy club_rulesets_service_role_all on public.club_rulesets
  for all to service_role
  using (true)
  with check (true);

-- ── club_tables ──
drop policy if exists club_tables_select on public.club_tables;
create policy club_tables_select on public.club_tables
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_tables_service_role_all on public.club_tables;
create policy club_tables_service_role_all on public.club_tables
  for all to service_role
  using (true)
  with check (true);

-- ── club_audit_log ──
drop policy if exists club_audit_log_select on public.club_audit_log;
create policy club_audit_log_select on public.club_audit_log
  for select to authenticated
  using (public.is_club_mod(club_id));

drop policy if exists club_audit_log_service_role_all on public.club_audit_log;
create policy club_audit_log_service_role_all on public.club_audit_log
  for all to service_role
  using (true)
  with check (true);
