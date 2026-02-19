-- Club Wallet Ledger + Leaderboard (V3)
-- Run after 006_gto_audit_pipeline.sql

-- ═══════════════════════════════════════════════════════════════
-- 1) Wallet ledger (append-only)
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.club_wallet_transactions (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  type varchar(24) not null check (
    type in (
      'deposit',
      'admin_grant',
      'admin_deduct',
      'buy_in',
      'cash_out',
      'transfer_in',
      'transfer_out',
      'adjustment'
    )
  ),
  amount bigint not null,
  currency varchar(16) not null default 'chips',
  ref_type varchar(40),
  ref_id text,
  created_at timestamptz not null default now(),
  created_by uuid references auth.users(id) on delete set null,
  note text,
  meta_json jsonb not null default '{}'::jsonb,
  idempotency_key text
);

create index if not exists idx_club_wallet_tx_club_user_time
  on public.club_wallet_transactions(club_id, user_id, created_at desc);

create index if not exists idx_club_wallet_tx_club_time
  on public.club_wallet_transactions(club_id, created_at desc);

create unique index if not exists idx_club_wallet_tx_idempotency
  on public.club_wallet_transactions(club_id, user_id, currency, idempotency_key)
  where idempotency_key is not null;

create or replace function public.club_wallet_tx_append_only_guard()
returns trigger
language plpgsql
as $$
begin
  raise exception 'club_wallet_transactions is append-only';
end;
$$;

drop trigger if exists trg_club_wallet_tx_no_update on public.club_wallet_transactions;
create trigger trg_club_wallet_tx_no_update
before update or delete on public.club_wallet_transactions
for each row execute function public.club_wallet_tx_append_only_guard();

-- ═══════════════════════════════════════════════════════════════
-- 2) Wallet balance cache (reconcilable with ledger)
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.club_wallet_accounts (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  currency varchar(16) not null default 'chips',
  current_balance bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (club_id, user_id, currency)
);

create index if not exists idx_club_wallet_accounts_club_user
  on public.club_wallet_accounts(club_id, user_id);

-- ═══════════════════════════════════════════════════════════════
-- 3) Daily player stats for leaderboard
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.club_player_daily_stats (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  day date not null,
  hands integer not null default 0,
  buy_in bigint not null default 0,
  cash_out bigint not null default 0,
  deposits bigint not null default 0,
  net bigint not null default 0,
  rake bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (club_id, user_id, day)
);

create index if not exists idx_club_daily_stats_club_day
  on public.club_player_daily_stats(club_id, day desc);

create index if not exists idx_club_daily_stats_user_day
  on public.club_player_daily_stats(user_id, day desc);

-- ═══════════════════════════════════════════════════════════════
-- 4) Atomic wallet append (ledger + account cache + tx-side stats)
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_wallet_append_tx(
  _club_id uuid,
  _user_id uuid,
  _type text,
  _amount bigint,
  _currency text default 'chips',
  _ref_type text default null,
  _ref_id text default null,
  _created_by uuid default null,
  _note text default null,
  _meta_json jsonb default '{}'::jsonb,
  _idempotency_key text default null
)
returns table (
  tx_id uuid,
  current_balance bigint,
  created_at timestamptz,
  was_duplicate boolean
)
language plpgsql
security invoker
as $$
declare
  v_existing_id uuid;
  v_existing_created timestamptz;
  v_balance bigint;
  v_created timestamptz;
  v_buy_in_delta bigint := 0;
  v_cash_out_delta bigint := 0;
  v_deposit_delta bigint := 0;
begin
  if _amount = 0 then
    raise exception 'wallet_tx_amount_must_be_non_zero';
  end if;

  if _idempotency_key is not null then
    select id, created_at
      into v_existing_id, v_existing_created
    from public.club_wallet_transactions
    where club_id = _club_id
      and user_id = _user_id
      and currency = _currency
      and idempotency_key = _idempotency_key
    limit 1;

    if v_existing_id is not null then
      insert into public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
      values (_club_id, _user_id, _currency, 0, now())
      on conflict (club_id, user_id, currency) do nothing;

      select current_balance into v_balance
      from public.club_wallet_accounts
      where club_id = _club_id
        and user_id = _user_id
        and currency = _currency;

      return query
      select v_existing_id, coalesce(v_balance, 0), v_existing_created, true;
      return;
    end if;
  end if;

  -- Lock account row to keep balance updates serialized.
  insert into public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  values (_club_id, _user_id, _currency, 0, now())
  on conflict (club_id, user_id, currency) do nothing;

  select current_balance into v_balance
  from public.club_wallet_accounts
  where club_id = _club_id
    and user_id = _user_id
    and currency = _currency
  for update;

  if coalesce(v_balance, 0) + _amount < 0 then
    raise exception 'insufficient_wallet_balance';
  end if;

  insert into public.club_wallet_transactions (
    club_id,
    user_id,
    type,
    amount,
    currency,
    ref_type,
    ref_id,
    created_by,
    note,
    meta_json,
    idempotency_key
  )
  values (
    _club_id,
    _user_id,
    _type,
    _amount,
    _currency,
    _ref_type,
    _ref_id,
    _created_by,
    _note,
    coalesce(_meta_json, '{}'::jsonb),
    _idempotency_key
  )
  returning id, created_at into tx_id, v_created;

  update public.club_wallet_accounts
  set current_balance = coalesce(current_balance, 0) + _amount,
      updated_at = now()
  where club_id = _club_id
    and user_id = _user_id
    and currency = _currency
  returning current_balance into v_balance;

  -- Tx-side aggregates (hands/net are updated by hand-end pipeline).
  if _type = 'buy_in' then
    v_buy_in_delta := abs(_amount);
  elsif _type = 'cash_out' then
    v_cash_out_delta := abs(_amount);
  elsif _type in ('deposit', 'admin_grant') and _amount > 0 then
    v_deposit_delta := _amount;
  end if;

  if v_buy_in_delta <> 0 or v_cash_out_delta <> 0 or v_deposit_delta <> 0 then
    insert into public.club_player_daily_stats (
      club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake, updated_at
    )
    values (
      _club_id, _user_id, now()::date, 0, v_buy_in_delta, v_cash_out_delta, v_deposit_delta, 0, 0, now()
    )
    on conflict (club_id, user_id, day) do update
    set buy_in = public.club_player_daily_stats.buy_in + excluded.buy_in,
        cash_out = public.club_player_daily_stats.cash_out + excluded.cash_out,
        deposits = public.club_player_daily_stats.deposits + excluded.deposits,
        updated_at = now();
  end if;

  return query
  select tx_id, v_balance, v_created, false;
end;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5) Hand-end stats upsert (hands + net + rake)
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_record_hand_stats(
  _club_id uuid,
  _user_id uuid,
  _hands_delta integer,
  _net_delta bigint,
  _rake_delta bigint default 0
)
returns void
language plpgsql
security invoker
as $$
begin
  insert into public.club_player_daily_stats (
    club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake, updated_at
  )
  values (
    _club_id,
    _user_id,
    now()::date,
    coalesce(_hands_delta, 0),
    0,
    0,
    0,
    coalesce(_net_delta, 0),
    coalesce(_rake_delta, 0),
    now()
  )
  on conflict (club_id, user_id, day) do update
  set hands = public.club_player_daily_stats.hands + excluded.hands,
      net = public.club_player_daily_stats.net + excluded.net,
      rake = public.club_player_daily_stats.rake + excluded.rake,
      updated_at = now();
end;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 6) Leaderboard query RPC
-- ═══════════════════════════════════════════════════════════════

create or replace function public.club_get_leaderboard(
  _club_id uuid,
  _day_from date,
  _metric text default 'net',
  _limit integer default 50
)
returns table (
  rank integer,
  club_id uuid,
  user_id uuid,
  display_name text,
  metric text,
  metric_value bigint,
  hands bigint,
  buy_in bigint,
  cash_out bigint,
  deposits bigint,
  net bigint
)
language sql
stable
security invoker
as $$
  with agg as (
    select
      s.club_id,
      s.user_id,
      sum(s.hands)::bigint as hands,
      sum(s.buy_in)::bigint as buy_in,
      sum(s.cash_out)::bigint as cash_out,
      sum(s.deposits)::bigint as deposits,
      sum(s.net)::bigint as net
    from public.club_player_daily_stats s
    where s.club_id = _club_id
      and s.day >= _day_from
    group by s.club_id, s.user_id
  ),
  scored as (
    select
      a.*,
      case
        when _metric = 'hands' then a.hands
        when _metric = 'buyin' then a.buy_in
        when _metric = 'deposits' then a.deposits
        else a.net
      end as metric_value
    from agg a
  ),
  ranked as (
    select
      row_number() over (order by s.metric_value desc, s.user_id) as rank,
      s.club_id,
      s.user_id,
      s.metric_value,
      s.hands,
      s.buy_in,
      s.cash_out,
      s.deposits,
      s.net
    from scored s
  )
  select
    r.rank,
    r.club_id,
    r.user_id,
    pp.display_name,
    _metric as metric,
    r.metric_value,
    r.hands,
    r.buy_in,
    r.cash_out,
    r.deposits,
    r.net
  from ranked r
  left join public.player_profiles pp on pp.user_id = r.user_id
  where r.rank <= greatest(1, least(coalesce(_limit, 50), 200));
$$;

-- ═══════════════════════════════════════════════════════════════
-- 7) RLS
-- ═══════════════════════════════════════════════════════════════

alter table public.club_wallet_transactions enable row level security;
alter table public.club_wallet_accounts enable row level security;
alter table public.club_player_daily_stats enable row level security;

drop policy if exists club_wallet_tx_select on public.club_wallet_transactions;
create policy club_wallet_tx_select on public.club_wallet_transactions
  for select to authenticated
  using (
    public.is_club_member(club_id)
    and (user_id = auth.uid() or public.is_club_admin(club_id))
  );

drop policy if exists club_wallet_tx_write_service on public.club_wallet_transactions;
create policy club_wallet_tx_write_service on public.club_wallet_transactions
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists club_wallet_accounts_select on public.club_wallet_accounts;
create policy club_wallet_accounts_select on public.club_wallet_accounts
  for select to authenticated
  using (
    public.is_club_member(club_id)
    and (user_id = auth.uid() or public.is_club_admin(club_id))
  );

drop policy if exists club_wallet_accounts_write_service on public.club_wallet_accounts;
create policy club_wallet_accounts_write_service on public.club_wallet_accounts
  for all
  to service_role
  using (true)
  with check (true);

drop policy if exists club_player_daily_stats_select on public.club_player_daily_stats;
create policy club_player_daily_stats_select on public.club_player_daily_stats
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists club_player_daily_stats_write_service on public.club_player_daily_stats;
create policy club_player_daily_stats_write_service on public.club_player_daily_stats
  for all
  to service_role
  using (true)
  with check (true);
