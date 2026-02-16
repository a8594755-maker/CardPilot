-- GTO Audit Pipeline: decision_points, gto_audits, session_leak_summaries
-- Run after 005_clubs.sql
-- Stores hero decision points captured during play and GTO audit results.

-- ── Decision Points ──
-- One row per hero decision (action) within a hand.

create table if not exists public.decision_points (
  id uuid primary key default gen_random_uuid(),
  hand_history_id uuid not null references public.hand_histories(id) on delete cascade,
  hand_id text not null,
  hero_user_id uuid not null references auth.users(id) on delete cascade,
  hero_seat smallint not null,
  hero_position varchar(4) not null,
  hero_cards jsonb not null default '[]'::jsonb,
  street varchar(12) not null,
  board jsonb not null default '[]'::jsonb,
  pot numeric not null default 0,
  to_call numeric not null default 0,
  effective_stack_bb numeric not null default 0,
  stack_depth_category varchar(10) not null default 'standard',
  actual_action varchar(10) not null,
  actual_amount numeric not null default 0,
  spot_type varchar(16) not null default 'SRP',
  line_tags jsonb not null default '[]'::jsonb,
  action_index smallint not null default 0,
  created_at timestamptz not null default now(),

  check (jsonb_typeof(hero_cards) = 'array'),
  check (jsonb_typeof(board) = 'array'),
  check (jsonb_typeof(line_tags) = 'array')
);

create index if not exists idx_decision_points_hand
  on public.decision_points(hand_history_id);

create index if not exists idx_decision_points_user_time
  on public.decision_points(hero_user_id, created_at desc);

create index if not exists idx_decision_points_user_street
  on public.decision_points(hero_user_id, street);

-- ── GTO Audit Results ──
-- One row per audited decision point (computed after hand ends).

create table if not exists public.gto_audits (
  id uuid primary key default gen_random_uuid(),
  decision_point_id uuid not null references public.decision_points(id) on delete cascade,
  hand_id text not null,
  hero_user_id uuid not null references auth.users(id) on delete cascade,

  -- GTO recommendation
  gto_mix_raise numeric not null default 0,
  gto_mix_call numeric not null default 0,
  gto_mix_fold numeric not null default 0,
  recommended_action varchar(10) not null,

  -- What hero did
  actual_action varchar(10) not null,

  -- Deviation metrics
  deviation_score numeric not null default 0,
  ev_diff_bb numeric not null default 0,
  ev_diff_chips numeric not null default 0,
  deviation_type varchar(16) not null default 'CORRECT',

  -- Context (denormalized for fast dashboard queries)
  street varchar(12) not null,
  spot_type varchar(16) not null default 'SRP',
  line_tags jsonb not null default '[]'::jsonb,
  hero_position varchar(4) not null,
  stack_depth_category varchar(10) not null default 'standard',

  -- Math context
  equity numeric,
  mdf numeric,
  alpha numeric,

  computed_at timestamptz not null default now(),

  unique (decision_point_id)
);

create index if not exists idx_gto_audits_user_time
  on public.gto_audits(hero_user_id, computed_at desc);

create index if not exists idx_gto_audits_user_street
  on public.gto_audits(hero_user_id, street);

create index if not exists idx_gto_audits_user_spot
  on public.gto_audits(hero_user_id, spot_type);

create index if not exists idx_gto_audits_user_deviation
  on public.gto_audits(hero_user_id, deviation_type);

create index if not exists idx_gto_audits_hand
  on public.gto_audits(hand_id);

-- ── Session Leak Summaries ──
-- Materialized aggregate per (session, user). Updated incrementally as hands complete.

create table if not exists public.session_leak_summaries (
  id uuid primary key default gen_random_uuid(),
  room_session_id uuid not null references public.room_sessions(id) on delete cascade,
  hero_user_id uuid not null references auth.users(id) on delete cascade,

  total_leaked_bb numeric not null default 0,
  total_leaked_chips numeric not null default 0,
  hands_played integer not null default 0,
  hands_audited integer not null default 0,
  leaked_bb_per_100 numeric not null default 0,

  -- JSONB breakdown buckets (lightweight; full detail in gto_audits)
  by_street jsonb not null default '{}'::jsonb,
  by_spot_type jsonb not null default '{}'::jsonb,
  by_line_tag jsonb not null default '{}'::jsonb,
  by_deviation jsonb not null default '{}'::jsonb,
  top_leaks jsonb not null default '[]'::jsonb,
  suggested_drills jsonb not null default '[]'::jsonb,

  updated_at timestamptz not null default now(),

  unique (room_session_id, hero_user_id)
);

create index if not exists idx_session_leak_user_time
  on public.session_leak_summaries(hero_user_id, updated_at desc);

-- ── Club Training Metrics (Phase 3 placeholder) ──

create table if not exists public.club_training_metrics (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  gto_adherence_score numeric not null default 50,
  leaked_bb_per_100 numeric not null default 0,
  hands_analyzed integer not null default 0,
  top_leaks jsonb not null default '[]'::jsonb,
  improvement_trend_pct numeric not null default 0,
  updated_at timestamptz not null default now(),

  unique (club_id, user_id)
);

create index if not exists idx_club_training_club
  on public.club_training_metrics(club_id);

-- ── Scenario Shares (Phase 1 placeholder) ──

create table if not exists public.scenario_shares (
  id uuid primary key default gen_random_uuid(),
  creator_user_id uuid not null references auth.users(id) on delete set null,
  hand_history_id uuid references public.hand_histories(id) on delete set null,
  decision_point_id uuid references public.decision_points(id) on delete set null,
  -- Compact payload: serialized hand + audit + optional exploit settings
  payload_json jsonb not null default '{}'::jsonb,
  -- Access control
  is_public boolean not null default true,
  club_id uuid,
  created_at timestamptz not null default now(),
  expires_at timestamptz
);

create index if not exists idx_scenario_shares_creator
  on public.scenario_shares(creator_user_id, created_at desc);

-- ── RLS Policies ──

alter table public.decision_points enable row level security;
alter table public.gto_audits enable row level security;
alter table public.session_leak_summaries enable row level security;
alter table public.club_training_metrics enable row level security;
alter table public.scenario_shares enable row level security;

-- Decision points: users see their own
drop policy if exists decision_points_select_own on public.decision_points;
create policy decision_points_select_own
  on public.decision_points for select to authenticated
  using (hero_user_id = auth.uid());

-- GTO audits: users see their own
drop policy if exists gto_audits_select_own on public.gto_audits;
create policy gto_audits_select_own
  on public.gto_audits for select to authenticated
  using (hero_user_id = auth.uid());

-- Session leak summaries: users see their own
drop policy if exists session_leak_summaries_select_own on public.session_leak_summaries;
create policy session_leak_summaries_select_own
  on public.session_leak_summaries for select to authenticated
  using (hero_user_id = auth.uid());

-- Club training metrics: users see their own + club admins see club members (via app-level gating)
drop policy if exists club_training_metrics_select_own on public.club_training_metrics;
create policy club_training_metrics_select_own
  on public.club_training_metrics for select to authenticated
  using (user_id = auth.uid());

-- Scenario shares: public shares visible to all, private only to creator
drop policy if exists scenario_shares_select on public.scenario_shares;
create policy scenario_shares_select
  on public.scenario_shares for select to authenticated
  using (is_public = true or creator_user_id = auth.uid());

-- Service role write access for all audit tables
drop policy if exists decision_points_write_service on public.decision_points;
create policy decision_points_write_service
  on public.decision_points for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists gto_audits_write_service on public.gto_audits;
create policy gto_audits_write_service
  on public.gto_audits for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists session_leak_write_service on public.session_leak_summaries;
create policy session_leak_write_service
  on public.session_leak_summaries for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists club_training_write_service on public.club_training_metrics;
create policy club_training_write_service
  on public.club_training_metrics for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists scenario_shares_write_service on public.scenario_shares;
create policy scenario_shares_write_service
  on public.scenario_shares for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

-- ── RPC: Get session leak summary ──

create or replace function public.get_session_leak_summary(
  _user_id uuid,
  _room_session_id uuid
)
returns table (
  total_leaked_bb numeric,
  total_leaked_chips numeric,
  hands_played integer,
  hands_audited integer,
  leaked_bb_per_100 numeric,
  by_street jsonb,
  by_spot_type jsonb,
  by_line_tag jsonb,
  by_deviation jsonb,
  top_leaks jsonb,
  suggested_drills jsonb,
  updated_at timestamptz
)
language sql
stable
as $$
  with actor as (
    select case
      when auth.role() = 'service_role' then _user_id
      else auth.uid()
    end as user_id
  )
  select
    sls.total_leaked_bb,
    sls.total_leaked_chips,
    sls.hands_played,
    sls.hands_audited,
    sls.leaked_bb_per_100,
    sls.by_street,
    sls.by_spot_type,
    sls.by_line_tag,
    sls.by_deviation,
    sls.top_leaks,
    sls.suggested_drills,
    sls.updated_at
  from public.session_leak_summaries sls
  join actor on actor.user_id = sls.hero_user_id
  where sls.room_session_id = _room_session_id
  limit 1;
$$;

-- ── RPC: Get hand audits for a specific hand ──

create or replace function public.get_hand_audits(
  _user_id uuid,
  _hand_id text
)
returns table (
  audit_id uuid,
  decision_point_id uuid,
  street varchar,
  actual_action varchar,
  recommended_action varchar,
  gto_mix_raise numeric,
  gto_mix_call numeric,
  gto_mix_fold numeric,
  deviation_score numeric,
  ev_diff_bb numeric,
  deviation_type varchar,
  spot_type varchar,
  line_tags jsonb,
  hero_position varchar,
  equity numeric,
  mdf numeric,
  computed_at timestamptz
)
language sql
stable
as $$
  with actor as (
    select case
      when auth.role() = 'service_role' then _user_id
      else auth.uid()
    end as user_id
  )
  select
    ga.id as audit_id,
    ga.decision_point_id,
    ga.street,
    ga.actual_action,
    ga.recommended_action,
    ga.gto_mix_raise,
    ga.gto_mix_call,
    ga.gto_mix_fold,
    ga.deviation_score,
    ga.ev_diff_bb,
    ga.deviation_type,
    ga.spot_type,
    ga.line_tags,
    ga.hero_position,
    ga.equity,
    ga.mdf,
    ga.computed_at
  from public.gto_audits ga
  join actor on actor.user_id = ga.hero_user_id
  where ga.hand_id = _hand_id
  order by ga.computed_at;
$$;

-- Grant execute permissions
revoke all on function public.get_session_leak_summary(uuid, uuid) from public;
revoke all on function public.get_hand_audits(uuid, text) from public;

grant execute on function public.get_session_leak_summary(uuid, uuid) to service_role;
grant execute on function public.get_session_leak_summary(uuid, uuid) to authenticated;
grant execute on function public.get_hand_audits(uuid, text) to service_role;
grant execute on function public.get_hand_audits(uuid, text) to authenticated;
