-- Hand history grouped by room and room session
-- Run after 003_lobby_room_code.sql

alter table public.live_tables
  add column if not exists created_by uuid references auth.users(id) on delete set null;

create table if not exists public.room_sessions (
  id uuid primary key default gen_random_uuid(),
  room_id text not null references public.live_tables(id) on delete cascade,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  started_hand_count integer not null default 0,
  ended_hand_count integer not null default 0,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_room_sessions_room_opened_desc
  on public.room_sessions(room_id, opened_at desc);

create unique index if not exists idx_room_sessions_one_open_per_room
  on public.room_sessions(room_id)
  where closed_at is null;

create table if not exists public.hand_histories (
  id uuid primary key default gen_random_uuid(),
  room_id text not null references public.live_tables(id) on delete cascade,
  room_session_id uuid not null references public.room_sessions(id) on delete cascade,
  hand_id text not null,
  hand_no integer not null check (hand_no > 0),
  ended_at timestamptz not null default now(),
  blinds_json jsonb not null default '{}'::jsonb,
  players_summary_json jsonb not null default '[]'::jsonb,
  summary_json jsonb not null default '{}'::jsonb,
  detail_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (room_id, hand_id),
  unique (room_session_id, hand_no),
  check (jsonb_typeof(blinds_json) = 'object'),
  check (jsonb_typeof(players_summary_json) = 'array'),
  check (jsonb_typeof(summary_json) = 'object'),
  check (jsonb_typeof(detail_json) = 'object')
);

create index if not exists idx_hand_histories_session_ended_desc
  on public.hand_histories(room_session_id, ended_at desc);

create index if not exists idx_hand_histories_room_ended_desc
  on public.hand_histories(room_id, ended_at desc);

create table if not exists public.user_hand_index (
  user_id uuid not null references auth.users(id) on delete cascade,
  room_id text not null references public.live_tables(id) on delete cascade,
  room_session_id uuid not null references public.room_sessions(id) on delete cascade,
  hand_history_id uuid not null references public.hand_histories(id) on delete cascade,
  ended_at timestamptz not null,
  primary key (user_id, hand_history_id)
);

create index if not exists idx_user_hand_index_user_room_time
  on public.user_hand_index(user_id, room_id, ended_at desc);

create index if not exists idx_user_hand_index_user_session_time
  on public.user_hand_index(user_id, room_session_id, ended_at desc);

create index if not exists idx_user_hand_index_session_time
  on public.user_hand_index(room_session_id, ended_at desc);

alter table public.room_sessions enable row level security;
alter table public.hand_histories enable row level security;
alter table public.user_hand_index enable row level security;

drop policy if exists room_sessions_select_visible_to_user on public.room_sessions;
create policy room_sessions_select_visible_to_user
  on public.room_sessions
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.user_hand_index uhi
      where uhi.room_session_id = room_sessions.id
        and uhi.user_id = auth.uid()
    )
  );

drop policy if exists hand_histories_select_visible_to_user on public.hand_histories;
create policy hand_histories_select_visible_to_user
  on public.hand_histories
  for select
  to authenticated
  using (
    exists (
      select 1
      from public.user_hand_index uhi
      where uhi.hand_history_id = hand_histories.id
        and uhi.user_id = auth.uid()
    )
  );

drop policy if exists user_hand_index_select_own on public.user_hand_index;
create policy user_hand_index_select_own
  on public.user_hand_index
  for select
  to authenticated
  using (user_id = auth.uid());

drop policy if exists room_sessions_write_service_role on public.room_sessions;
create policy room_sessions_write_service_role
  on public.room_sessions
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists hand_histories_write_service_role on public.hand_histories;
create policy hand_histories_write_service_role
  on public.hand_histories
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists user_hand_index_write_service_role on public.user_hand_index;
create policy user_hand_index_write_service_role
  on public.user_hand_index
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create or replace function public.open_room_session(
  _room_id text,
  _metadata_json jsonb default '{}'::jsonb
)
returns uuid
language plpgsql
as $$
declare
  v_session_id uuid;
  v_started_count integer;
begin
  select id
  into v_session_id
  from public.room_sessions
  where room_id = _room_id
    and closed_at is null
  order by opened_at desc
  limit 1;

  if v_session_id is not null then
    return v_session_id;
  end if;

  select coalesce(sum(ended_hand_count), 0)
  into v_started_count
  from public.room_sessions
  where room_id = _room_id;

  insert into public.room_sessions (
    room_id,
    opened_at,
    closed_at,
    started_hand_count,
    ended_hand_count,
    metadata_json
  )
  values (
    _room_id,
    now(),
    null,
    v_started_count,
    0,
    coalesce(_metadata_json, '{}'::jsonb)
  )
  returning id into v_session_id;

  return v_session_id;
end;
$$;

create or replace function public.close_room_session(
  _room_id text,
  _metadata_json jsonb default null
)
returns uuid
language plpgsql
as $$
declare
  v_session_id uuid;
begin
  select id
  into v_session_id
  from public.room_sessions
  where room_id = _room_id
    and closed_at is null
  order by opened_at desc
  limit 1;

  if v_session_id is null then
    return null;
  end if;

  update public.room_sessions
  set
    closed_at = now(),
    metadata_json = case
      when _metadata_json is null then metadata_json
      else coalesce(metadata_json, '{}'::jsonb) || _metadata_json
    end
  where id = v_session_id;

  return v_session_id;
end;
$$;

create or replace function public.record_hand_history(
  _room_id text,
  _hand_id text,
  _ended_at timestamptz,
  _blinds_json jsonb,
  _players_summary_json jsonb,
  _summary_json jsonb,
  _detail_json jsonb,
  _viewer_user_ids uuid[],
  _session_metadata_json jsonb default '{}'::jsonb
)
returns table (
  hand_history_id uuid,
  room_session_id uuid,
  hand_no integer,
  inserted boolean
)
language plpgsql
as $$
declare
  v_session_id uuid;
  v_hand_history_id uuid;
  v_hand_no integer;
  v_ended_at timestamptz;
begin
  v_ended_at := coalesce(_ended_at, now());
  v_session_id := public.open_room_session(_room_id, _session_metadata_json);

  select id, hand_no
  into v_hand_history_id, v_hand_no
  from public.hand_histories
  where room_id = _room_id
    and hand_id = _hand_id
  limit 1;

  if v_hand_history_id is not null then
    return query
    select v_hand_history_id, v_session_id, v_hand_no, false;
    return;
  end if;

  select ended_hand_count
  into v_hand_no
  from public.room_sessions
  where id = v_session_id
  for update;

  v_hand_no := coalesce(v_hand_no, 0) + 1;

  begin
    insert into public.hand_histories (
      room_id,
      room_session_id,
      hand_id,
      hand_no,
      ended_at,
      blinds_json,
      players_summary_json,
      summary_json,
      detail_json
    )
    values (
      _room_id,
      v_session_id,
      _hand_id,
      v_hand_no,
      v_ended_at,
      coalesce(_blinds_json, '{}'::jsonb),
      coalesce(_players_summary_json, '[]'::jsonb),
      coalesce(_summary_json, '{}'::jsonb),
      coalesce(_detail_json, '{}'::jsonb)
    )
    returning id into v_hand_history_id;
  exception
    when unique_violation then
      select id, hand_no
      into v_hand_history_id, v_hand_no
      from public.hand_histories
      where room_id = _room_id
        and hand_id = _hand_id
      limit 1;

      return query
      select v_hand_history_id, v_session_id, v_hand_no, false;
      return;
  end;

  update public.room_sessions
  set ended_hand_count = greatest(ended_hand_count, v_hand_no)
  where id = v_session_id;

  if _viewer_user_ids is not null and array_length(_viewer_user_ids, 1) is not null then
    insert into public.user_hand_index (
      user_id,
      room_id,
      room_session_id,
      hand_history_id,
      ended_at
    )
    select distinct
      uid,
      _room_id,
      v_session_id,
      v_hand_history_id,
      v_ended_at
    from unnest(_viewer_user_ids) as uid
    on conflict (user_id, hand_history_id) do nothing;
  end if;

  return query
  select v_hand_history_id, v_session_id, v_hand_no, true;
end;
$$;

create or replace function public.history_list_rooms(
  _user_id uuid,
  _limit integer default 50
)
returns table (
  room_id text,
  room_code varchar,
  room_name varchar,
  last_played_at timestamptz,
  total_hands bigint
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
    uhi.room_id,
    lt.room_code,
    lt.room_name,
    max(uhi.ended_at) as last_played_at,
    count(*)::bigint as total_hands
  from public.user_hand_index uhi
  join actor on actor.user_id = uhi.user_id
  join public.live_tables lt on lt.id = uhi.room_id
  group by uhi.room_id, lt.room_code, lt.room_name
  order by max(uhi.ended_at) desc
  limit greatest(1, least(coalesce(_limit, 50), 200));
$$;

create or replace function public.history_list_sessions(
  _user_id uuid,
  _room_id text,
  _limit integer default 100
)
returns table (
  room_session_id uuid,
  room_id text,
  opened_at timestamptz,
  closed_at timestamptz,
  hand_count bigint,
  started_hand_count integer,
  ended_hand_count integer,
  metadata_json jsonb
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
    rs.id as room_session_id,
    rs.room_id,
    rs.opened_at,
    rs.closed_at,
    count(uhi.hand_history_id)::bigint as hand_count,
    rs.started_hand_count,
    rs.ended_hand_count,
    rs.metadata_json
  from public.room_sessions rs
  join public.user_hand_index uhi
    on uhi.room_session_id = rs.id
  join actor
    on actor.user_id = uhi.user_id
  where rs.room_id = _room_id
  group by rs.id, rs.room_id, rs.opened_at, rs.closed_at, rs.started_hand_count, rs.ended_hand_count, rs.metadata_json
  order by rs.opened_at desc
  limit greatest(1, least(coalesce(_limit, 100), 500));
$$;

create or replace function public.history_list_hands(
  _user_id uuid,
  _room_session_id uuid,
  _limit integer default 50,
  _before_ended_at timestamptz default null
)
returns table (
  hand_history_id uuid,
  room_id text,
  room_session_id uuid,
  hand_id text,
  hand_no integer,
  ended_at timestamptz,
  blinds_json jsonb,
  players_summary_json jsonb,
  summary_json jsonb
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
    hh.id as hand_history_id,
    hh.room_id,
    hh.room_session_id,
    hh.hand_id,
    hh.hand_no,
    hh.ended_at,
    hh.blinds_json,
    hh.players_summary_json,
    hh.summary_json
  from public.hand_histories hh
  join public.user_hand_index uhi
    on uhi.hand_history_id = hh.id
  join actor
    on actor.user_id = uhi.user_id
  where hh.room_session_id = _room_session_id
    and (_before_ended_at is null or hh.ended_at < _before_ended_at)
  order by hh.ended_at desc
  limit greatest(1, least(coalesce(_limit, 50), 200));
$$;

create or replace function public.history_get_hand_detail(
  _user_id uuid,
  _hand_history_id uuid
)
returns table (
  hand_history_id uuid,
  room_id text,
  room_session_id uuid,
  hand_id text,
  hand_no integer,
  ended_at timestamptz,
  blinds_json jsonb,
  players_summary_json jsonb,
  summary_json jsonb,
  detail_json jsonb
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
    hh.id as hand_history_id,
    hh.room_id,
    hh.room_session_id,
    hh.hand_id,
    hh.hand_no,
    hh.ended_at,
    hh.blinds_json,
    hh.players_summary_json,
    hh.summary_json,
    hh.detail_json
  from public.hand_histories hh
  join public.user_hand_index uhi
    on uhi.hand_history_id = hh.id
  join actor
    on actor.user_id = uhi.user_id
  where hh.id = _hand_history_id
  limit 1;
$$;

revoke all on function public.open_room_session(text, jsonb) from public;
revoke all on function public.close_room_session(text, jsonb) from public;
revoke all on function public.record_hand_history(text, text, timestamptz, jsonb, jsonb, jsonb, jsonb, uuid[], jsonb) from public;
revoke all on function public.history_list_rooms(uuid, integer) from public;
revoke all on function public.history_list_sessions(uuid, text, integer) from public;
revoke all on function public.history_list_hands(uuid, uuid, integer, timestamptz) from public;
revoke all on function public.history_get_hand_detail(uuid, uuid) from public;

grant execute on function public.open_room_session(text, jsonb) to service_role;
grant execute on function public.close_room_session(text, jsonb) to service_role;
grant execute on function public.record_hand_history(text, text, timestamptz, jsonb, jsonb, jsonb, jsonb, uuid[], jsonb) to service_role;
grant execute on function public.history_list_rooms(uuid, integer) to service_role;
grant execute on function public.history_list_sessions(uuid, text, integer) to service_role;
grant execute on function public.history_list_hands(uuid, uuid, integer, timestamptz) to service_role;
grant execute on function public.history_get_hand_detail(uuid, uuid) to service_role;

grant execute on function public.history_list_rooms(uuid, integer) to authenticated;
grant execute on function public.history_list_sessions(uuid, text, integer) to authenticated;
grant execute on function public.history_list_hands(uuid, uuid, integer, timestamptz) to authenticated;
grant execute on function public.history_get_hand_detail(uuid, uuid) to authenticated;
