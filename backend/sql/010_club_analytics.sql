-- Club Analytics (V4)
-- Run after 009_chat_and_notifications.sql
-- Adds session-level stats, hourly activity, VPIP/PFR tracking,
-- and RPC functions for analytics queries.

-- ═══════════════════════════════════════════════════════════════
-- 1) Extend club_player_daily_stats with VPIP/PFR columns
-- ═══════════════════════════════════════════════════════════════

alter table public.club_player_daily_stats
  add column if not exists vpip_hands integer not null default 0,
  add column if not exists pfr_hands integer not null default 0,
  add column if not exists sessions integer not null default 0;

-- ═══════════════════════════════════════════════════════════════
-- 2) Player session stats (per-table session)
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.club_player_session_stats (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  table_id uuid not null,
  table_name text not null default '',
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  hands integer not null default 0,
  buy_in bigint not null default 0,
  cash_out bigint not null default 0,
  net bigint not null default 0,
  peak_stack bigint not null default 0,
  vpip_hands integer not null default 0,
  pfr_hands integer not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists idx_club_session_stats_club_user
  on public.club_player_session_stats(club_id, user_id, started_at desc);

create index if not exists idx_club_session_stats_club_time
  on public.club_player_session_stats(club_id, started_at desc);

create index if not exists idx_club_session_stats_user_time
  on public.club_player_session_stats(user_id, started_at desc);

-- ═══════════════════════════════════════════════════════════════
-- 3) Hourly activity heatmap
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.club_player_hourly_activity (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  day_of_week smallint not null check (day_of_week between 0 and 6),  -- 0=Sunday
  hour_of_day smallint not null check (hour_of_day between 0 and 23),
  hands integer not null default 0,
  net bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (club_id, user_id, day_of_week, hour_of_day)
);

-- ═══════════════════════════════════════════════════════════════
-- 4) Enhanced hand-end stats upsert (with VPIP/PFR)
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_record_hand_stats_v2(
  _club_id uuid,
  _user_id uuid,
  _hands_delta integer,
  _net_delta bigint,
  _rake_delta bigint default 0,
  _is_vpip boolean default false,
  _is_pfr boolean default false
)
returns void
language plpgsql
security invoker
as $$
begin
  insert into public.club_player_daily_stats (
    club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake,
    vpip_hands, pfr_hands, updated_at
  )
  values (
    _club_id,
    _user_id,
    now()::date,
    coalesce(_hands_delta, 0),
    0, 0, 0,
    coalesce(_net_delta, 0),
    coalesce(_rake_delta, 0),
    case when _is_vpip then 1 else 0 end,
    case when _is_pfr then 1 else 0 end,
    now()
  )
  on conflict (club_id, user_id, day) do update
  set hands = public.club_player_daily_stats.hands + excluded.hands,
      net = public.club_player_daily_stats.net + excluded.net,
      rake = public.club_player_daily_stats.rake + excluded.rake,
      vpip_hands = public.club_player_daily_stats.vpip_hands + excluded.vpip_hands,
      pfr_hands = public.club_player_daily_stats.pfr_hands + excluded.pfr_hands,
      updated_at = now();

  -- Update hourly activity
  insert into public.club_player_hourly_activity (
    club_id, user_id, day_of_week, hour_of_day, hands, net, updated_at
  )
  values (
    _club_id,
    _user_id,
    extract(dow from now())::smallint,
    extract(hour from now())::smallint,
    coalesce(_hands_delta, 0),
    coalesce(_net_delta, 0),
    now()
  )
  on conflict (club_id, user_id, day_of_week, hour_of_day) do update
  set hands = public.club_player_hourly_activity.hands + excluded.hands,
      net = public.club_player_hourly_activity.net + excluded.net,
      updated_at = now();
end;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5) Analytics RPC: Player stats aggregate
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_player_analytics(
  _club_id uuid,
  _user_id uuid,
  _day_from date default (now() - interval '30 days')::date
)
returns table (
  total_hands bigint,
  total_sessions bigint,
  total_buy_in bigint,
  total_cash_out bigint,
  total_net bigint,
  total_rake bigint,
  vpip_hands bigint,
  pfr_hands bigint,
  winning_days bigint,
  losing_days bigint,
  break_even_days bigint
)
language sql
stable
security invoker
as $$
  select
    coalesce(sum(s.hands), 0)::bigint as total_hands,
    coalesce(sum(s.sessions), 0)::bigint as total_sessions,
    coalesce(sum(s.buy_in), 0)::bigint as total_buy_in,
    coalesce(sum(s.cash_out), 0)::bigint as total_cash_out,
    coalesce(sum(s.net), 0)::bigint as total_net,
    coalesce(sum(s.rake), 0)::bigint as total_rake,
    coalesce(sum(s.vpip_hands), 0)::bigint as vpip_hands,
    coalesce(sum(s.pfr_hands), 0)::bigint as pfr_hands,
    count(*) filter (where s.net > 0) as winning_days,
    count(*) filter (where s.net < 0) as losing_days,
    count(*) filter (where s.net = 0 and s.hands > 0) as break_even_days
  from public.club_player_daily_stats s
  where s.club_id = _club_id
    and s.user_id = _user_id
    and s.day >= _day_from;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 6) Analytics RPC: Cumulative P&L over time
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_profit_over_time(
  _club_id uuid,
  _user_id uuid,
  _day_from date default (now() - interval '30 days')::date
)
returns table (
  day date,
  daily_net bigint,
  cumulative_net bigint,
  hands integer
)
language sql
stable
security invoker
as $$
  select
    s.day,
    s.net as daily_net,
    sum(s.net) over (order by s.day)::bigint as cumulative_net,
    s.hands
  from public.club_player_daily_stats s
  where s.club_id = _club_id
    and s.user_id = _user_id
    and s.day >= _day_from
  order by s.day;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 7) Analytics RPC: Hourly heatmap
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_hourly_heatmap(
  _club_id uuid,
  _user_id uuid
)
returns table (
  day_of_week smallint,
  hour_of_day smallint,
  hands integer,
  net bigint
)
language sql
stable
security invoker
as $$
  select
    h.day_of_week,
    h.hour_of_day,
    h.hands,
    h.net
  from public.club_player_hourly_activity h
  where h.club_id = _club_id
    and h.user_id = _user_id
  order by h.day_of_week, h.hour_of_day;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 8) Analytics RPC: Club overview (admin)
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_overview_analytics(
  _club_id uuid,
  _day_from date default (now() - interval '30 days')::date
)
returns table (
  total_hands bigint,
  unique_players bigint,
  total_buy_in bigint,
  total_cash_out bigint,
  total_rake bigint,
  total_sessions bigint,
  avg_hands_per_player numeric
)
language sql
stable
security invoker
as $$
  select
    coalesce(sum(s.hands), 0)::bigint as total_hands,
    count(distinct s.user_id)::bigint as unique_players,
    coalesce(sum(s.buy_in), 0)::bigint as total_buy_in,
    coalesce(sum(s.cash_out), 0)::bigint as total_cash_out,
    coalesce(sum(s.rake), 0)::bigint as total_rake,
    coalesce(sum(s.sessions), 0)::bigint as total_sessions,
    case when count(distinct s.user_id) > 0
      then round(sum(s.hands)::numeric / count(distinct s.user_id), 1)
      else 0
    end as avg_hands_per_player
  from public.club_player_daily_stats s
  where s.club_id = _club_id
    and s.day >= _day_from;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 9) Analytics RPC: Daily active players trend
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_active_players_trend(
  _club_id uuid,
  _day_from date default (now() - interval '30 days')::date
)
returns table (
  day date,
  active_players bigint,
  total_hands bigint,
  total_net bigint
)
language sql
stable
security invoker
as $$
  select
    s.day,
    count(distinct s.user_id)::bigint as active_players,
    sum(s.hands)::bigint as total_hands,
    sum(s.net)::bigint as total_net
  from public.club_player_daily_stats s
  where s.club_id = _club_id
    and s.day >= _day_from
    and s.hands > 0
  group by s.day
  order by s.day;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 10) RLS
-- ═══════════════════════════════════════════════════════════════

alter table public.club_player_session_stats enable row level security;
alter table public.club_player_hourly_activity enable row level security;

-- Session stats: members can see all club members' stats
drop policy if exists club_session_stats_select on public.club_player_session_stats;
create policy club_session_stats_select on public.club_player_session_stats
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_session_stats_write_service on public.club_player_session_stats;
create policy club_session_stats_write_service on public.club_player_session_stats
  for all
  to service_role
  using (true)
  with check (true);

-- Hourly activity: members can see all
drop policy if exists club_hourly_activity_select on public.club_player_hourly_activity;
create policy club_hourly_activity_select on public.club_player_hourly_activity
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_hourly_activity_write_service on public.club_player_hourly_activity;
create policy club_hourly_activity_write_service on public.club_player_hourly_activity
  for all
  to service_role
  using (true)
  with check (true);

-- ═══════════════════════════════════════════════════════════════
-- 11) GRANTS
-- ═══════════════════════════════════════════════════════════════

grant all on table public.club_player_session_stats to service_role;
grant all on table public.club_player_hourly_activity to service_role;
grant execute on function public.club_record_hand_stats_v2 to service_role, authenticated;
grant execute on function public.club_get_player_analytics to service_role, authenticated;
grant execute on function public.club_get_profit_over_time to service_role, authenticated;
grant execute on function public.club_get_hourly_heatmap to service_role, authenticated;
grant execute on function public.club_get_overview_analytics to service_role, authenticated;
grant execute on function public.club_get_active_players_trend to service_role, authenticated;
