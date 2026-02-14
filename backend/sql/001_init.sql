-- CardPilot MVP bootstrap schema
-- Target: PostgreSQL 15+

create extension if not exists "pgcrypto";

create type table_mode as enum ('CASUAL', 'TRAINING');
create type table_status as enum ('WAITING', 'RUNNING', 'PAUSED', 'CLOSED');
create type hand_street as enum ('PREFLOP', 'FLOP', 'TURN', 'RIVER', 'SHOWDOWN');
create type action_type as enum ('FOLD', 'CHECK', 'CALL', 'BET', 'RAISE', 'POST_SB', 'POST_BB', 'ALL_IN');
create type hand_end_reason as enum ('SHOWDOWN', 'ALL_FOLD', 'TIMEOUT', 'ADMIN_ABORT');

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  username varchar(32) not null unique,
  display_name varchar(64) not null,
  password_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists poker_tables (
  id uuid primary key default gen_random_uuid(),
  name varchar(80) not null,
  max_players smallint not null check (max_players between 2 and 9),
  small_blind integer not null check (small_blind > 0),
  big_blind integer not null check (big_blind > small_blind),
  min_buy_in integer not null check (min_buy_in > 0),
  max_buy_in integer not null check (max_buy_in >= min_buy_in),
  mode table_mode not null default 'CASUAL',
  status table_status not null default 'WAITING',
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists table_seats (
  id uuid primary key default gen_random_uuid(),
  table_id uuid not null references poker_tables(id) on delete cascade,
  seat_no smallint not null check (seat_no >= 1),
  user_id uuid references users(id),
  stack integer not null default 0 check (stack >= 0),
  is_sitting_out boolean not null default false,
  joined_at timestamptz not null default now(),
  left_at timestamptz,
  unique (table_id, seat_no)
);

create index if not exists idx_table_seats_table_id on table_seats(table_id);
create index if not exists idx_table_seats_user_id on table_seats(user_id);

create table if not exists hands (
  id uuid primary key default gen_random_uuid(),
  table_id uuid not null references poker_tables(id) on delete cascade,
  hand_no bigint not null,
  started_at timestamptz not null default now(),
  ended_at timestamptz,
  button_seat smallint not null,
  sb_amount integer not null,
  bb_amount integer not null,
  board_cards varchar(16) not null default '',
  total_pot integer not null default 0,
  rake integer not null default 0,
  end_reason hand_end_reason,
  deck_seed_hash text,
  unique (table_id, hand_no)
);

create index if not exists idx_hands_table_started_at on hands(table_id, started_at desc);

create table if not exists hand_players (
  id uuid primary key default gen_random_uuid(),
  hand_id uuid not null references hands(id) on delete cascade,
  seat_no smallint not null,
  user_id uuid references users(id),
  hole_cards varchar(8) not null default '',
  starting_stack integer not null check (starting_stack >= 0),
  ending_stack integer not null check (ending_stack >= 0),
  did_fold boolean not null default false,
  showed_down boolean not null default false,
  hand_rank integer,
  hand_label varchar(64),
  unique (hand_id, seat_no)
);

create index if not exists idx_hand_players_user_id on hand_players(user_id);

create table if not exists hand_actions (
  id uuid primary key default gen_random_uuid(),
  hand_id uuid not null references hands(id) on delete cascade,
  seq_no integer not null,
  street hand_street not null,
  seat_no smallint not null,
  action action_type not null,
  amount integer not null default 0 check (amount >= 0),
  to_amount integer,
  is_legal boolean not null default true,
  action_ts timestamptz not null default now(),
  unique (hand_id, seq_no)
);

create index if not exists idx_hand_actions_hand_id on hand_actions(hand_id, seq_no);

create table if not exists hand_results (
  id uuid primary key default gen_random_uuid(),
  hand_id uuid not null references hands(id) on delete cascade,
  seat_no smallint not null,
  user_id uuid references users(id),
  won_amount integer not null default 0,
  pot_share integer not null default 0,
  result_note varchar(128),
  unique (hand_id, seat_no)
);

create table if not exists preflop_charts (
  id uuid primary key default gen_random_uuid(),
  format varchar(20) not null,                   -- cash
  players varchar(10) not null,                  -- 6max / hu
  effective_stack_bb smallint not null,
  hero_pos varchar(5) not null,
  villain_pos varchar(5) not null,
  line varchar(20) not null,                     -- unopened / facing_open / facing_3bet / facing_4bet
  size_bucket varchar(20) not null,              -- open2.5x / 3bet9x / etc
  hand_code varchar(4) not null,                 -- A5s, KQo
  raise_freq numeric(5,4) not null default 0,
  call_freq numeric(5,4) not null default 0,
  fold_freq numeric(5,4) not null default 0,
  reason_tags text[] not null default '{}',
  created_at timestamptz not null default now(),
  check (raise_freq >= 0 and call_freq >= 0 and fold_freq >= 0),
  check (round((raise_freq + call_freq + fold_freq)::numeric, 4) = 1.0000),
  unique (format, players, effective_stack_bb, hero_pos, villain_pos, line, size_bucket, hand_code)
);

create index if not exists idx_preflop_lookup
  on preflop_charts(format, players, effective_stack_bb, hero_pos, villain_pos, line, size_bucket);

create table if not exists advice_logs (
  id uuid primary key default gen_random_uuid(),
  hand_id uuid not null references hands(id) on delete cascade,
  table_id uuid not null references poker_tables(id) on delete cascade,
  user_id uuid not null references users(id),
  seat_no smallint not null,
  street hand_street not null,
  spot_key varchar(128) not null,
  hero_hand varchar(4) not null,
  suggested_mix jsonb not null,
  explanation text,
  chosen_action action_type,
  chosen_amount integer,
  deviation_score numeric(6,4),
  created_at timestamptz not null default now()
);

create index if not exists idx_advice_logs_user_created on advice_logs(user_id, created_at desc);
create index if not exists idx_advice_logs_spot_key on advice_logs(spot_key);
