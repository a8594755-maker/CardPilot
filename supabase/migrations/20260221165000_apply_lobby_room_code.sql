-- Lobby + room code support
-- Run after 002_supabase_multiplayer.sql

alter table public.live_tables
  add column if not exists room_code varchar(12),
  add column if not exists room_name varchar(80) not null default 'Training Room',
  add column if not exists small_blind integer not null default 50,
  add column if not exists big_blind integer not null default 100,
  add column if not exists is_public boolean not null default true;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'live_tables_blind_check'
  ) then
    alter table public.live_tables
      add constraint live_tables_blind_check
      check (small_blind > 0 and big_blind > small_blind);
  end if;
end $$;

create unique index if not exists idx_live_tables_room_code_unique
  on public.live_tables(room_code)
  where room_code is not null;

create index if not exists idx_live_tables_lobby
  on public.live_tables(status, is_public, updated_at desc);

create index if not exists idx_live_table_seats_table_connected
  on public.live_table_seats(table_id, is_connected);
