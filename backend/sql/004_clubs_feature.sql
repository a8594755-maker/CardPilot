-- Club Feature V1 — Simplified schema (see 005_clubs.sql for full production schema)
-- This migration creates the core club tables required for Task A.
-- Run after 003_lobby_room_code.sql

-- ═══════════════════════════════════════════════════════════════
-- 1) clubs
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.clubs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name varchar(50) not null,
  description text not null default '',
  invite_code varchar(6) not null,
  currency_symbol varchar(4) not null default '💎',
  created_at timestamptz not null default now()
);

create unique index if not exists idx_clubs_invite_code on public.clubs(invite_code);
create index if not exists idx_clubs_owner_id on public.clubs(owner_id);

-- ═══════════════════════════════════════════════════════════════
-- 2) club_members
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_members (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role varchar(16) not null default 'MEMBER'
    check (role in ('OWNER', 'ADMIN', 'AGENT', 'MEMBER')),
  balance integer not null default 0,
  status varchar(16) not null default 'PENDING'
    check (status in ('PENDING', 'ACTIVE', 'BANNED')),
  notes text,
  created_at timestamptz not null default now(),
  primary key (club_id, user_id)
);

create index if not exists idx_club_members_user on public.club_members(user_id);
create index if not exists idx_club_members_status on public.club_members(club_id, status);

-- ═══════════════════════════════════════════════════════════════
-- 3) club_ledger — tracks all chip grants/deductions for audit
-- ═══════════════════════════════════════════════════════════════
create table if not exists public.club_ledger (
  id bigint generated always as identity primary key,
  club_id uuid not null references public.clubs(id) on delete cascade,
  actor_user_id uuid not null references auth.users(id) on delete cascade,
  target_user_id uuid not null references auth.users(id) on delete cascade,
  amount integer not null,
  balance_after integer not null,
  reason text not null default '',
  created_at timestamptz not null default now()
);

create index if not exists idx_club_ledger_club on public.club_ledger(club_id, created_at desc);
create index if not exists idx_club_ledger_target on public.club_ledger(target_user_id, created_at desc);

-- ═══════════════════════════════════════════════════════════════
-- 4) Update poker_tables — add club_id for club table linking
-- ═══════════════════════════════════════════════════════════════
-- Note: In the full schema (005_clubs.sql), club tables are tracked in a
-- separate club_tables table. This simpler approach adds club_id directly
-- to the live_tables table used by the game server.

do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema = 'public'
      and table_name = 'live_tables'
      and column_name = 'club_id'
  ) then
    alter table public.live_tables add column club_id uuid references public.clubs(id) on delete set null;
    create index idx_live_tables_club_id on public.live_tables(club_id) where club_id is not null;
  end if;
end $$;

-- ═══════════════════════════════════════════════════════════════
-- RLS
-- ═══════════════════════════════════════════════════════════════

alter table public.clubs enable row level security;
alter table public.club_members enable row level security;
alter table public.club_ledger enable row level security;

-- Service role has full access (server-side operations)
create policy if not exists clubs_service_all on public.clubs
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create policy if not exists club_members_service_all on public.club_members
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create policy if not exists club_ledger_service_all on public.club_ledger
  for all using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

-- Members can read their own club data
create policy if not exists clubs_select_member on public.clubs
  for select to authenticated
  using (
    owner_id = auth.uid()
    or exists (
      select 1 from public.club_members
      where club_id = clubs.id
        and user_id = auth.uid()
        and status = 'ACTIVE'
    )
  );

create policy if not exists club_members_select_member on public.club_members
  for select to authenticated
  using (
    user_id = auth.uid()
    or exists (
      select 1 from public.club_members cm
      where cm.club_id = club_members.club_id
        and cm.user_id = auth.uid()
        and cm.status = 'ACTIVE'
    )
  );
