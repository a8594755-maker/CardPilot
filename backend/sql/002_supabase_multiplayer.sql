-- Supabase multiplayer persistence schema
-- Run in Supabase SQL editor after 001_init.sql

create table if not exists public.player_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name varchar(32) not null,
  avatar_url text,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.live_tables (
  id text primary key,
  status varchar(16) not null default 'OPEN',
  max_players smallint not null default 6,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.live_table_seats (
  table_id text not null references public.live_tables(id) on delete cascade,
  seat_no smallint not null check (seat_no between 1 and 9),
  user_id uuid not null references auth.users(id) on delete cascade,
  display_name varchar(32) not null,
  stack integer not null check (stack >= 0),
  is_connected boolean not null default true,
  updated_at timestamptz not null default now(),
  primary key (table_id, seat_no),
  unique (table_id, user_id)
);

create index if not exists idx_live_table_seats_user_id on public.live_table_seats(user_id);

create table if not exists public.live_table_events (
  id bigint generated always as identity primary key,
  table_id text not null references public.live_tables(id) on delete cascade,
  hand_id text,
  event_type varchar(40) not null,
  actor_user_id uuid references auth.users(id) on delete set null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_live_table_events_table_time on public.live_table_events(table_id, created_at desc);

alter table public.player_profiles enable row level security;
alter table public.live_tables enable row level security;
alter table public.live_table_seats enable row level security;
alter table public.live_table_events enable row level security;

-- Read access for authenticated clients (e.g. lobby / observer UI)
drop policy if exists player_profiles_select_authenticated on public.player_profiles;
create policy player_profiles_select_authenticated
  on public.player_profiles
  for select
  to authenticated
  using (true);

drop policy if exists live_tables_select_authenticated on public.live_tables;
create policy live_tables_select_authenticated
  on public.live_tables
  for select
  to authenticated
  using (true);

drop policy if exists live_table_seats_select_authenticated on public.live_table_seats;
create policy live_table_seats_select_authenticated
  on public.live_table_seats
  for select
  to authenticated
  using (true);

drop policy if exists live_table_events_select_authenticated on public.live_table_events;
create policy live_table_events_select_authenticated
  on public.live_table_events
  for select
  to authenticated
  using (true);

-- Write access only via server using service role key
drop policy if exists player_profiles_write_service_role on public.player_profiles;
create policy player_profiles_write_service_role
  on public.player_profiles
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists live_tables_write_service_role on public.live_tables;
create policy live_tables_write_service_role
  on public.live_tables
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists live_table_seats_write_service_role on public.live_table_seats;
create policy live_table_seats_write_service_role
  on public.live_table_seats
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

drop policy if exists live_table_events_write_service_role on public.live_table_events;
create policy live_table_events_write_service_role
  on public.live_table_events
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');
