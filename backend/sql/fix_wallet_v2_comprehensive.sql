-- Comprehensive Fix for Club Wallet (Tables, RPCs, Permissions)
-- Run this in Supabase SQL Editor to resolve "Wallet transaction failed" errors.

BEGIN;

-- 1. Ensure Tables Exist
CREATE TABLE IF NOT EXISTS public.club_wallet_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type varchar(24) NOT NULL CHECK (type IN ('deposit', 'admin_grant', 'admin_deduct', 'buy_in', 'cash_out', 'transfer_in', 'transfer_out', 'adjustment')),
  amount bigint NOT NULL,
  currency varchar(16) NOT NULL DEFAULT 'chips',
  ref_type varchar(40),
  ref_id text,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  note text,
  meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text
);

CREATE TABLE IF NOT EXISTS public.club_wallet_accounts (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  currency varchar(16) NOT NULL DEFAULT 'chips',
  current_balance bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id, currency)
);

CREATE TABLE IF NOT EXISTS public.club_player_daily_stats (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  day date NOT NULL,
  hands integer NOT NULL DEFAULT 0,
  buy_in bigint NOT NULL DEFAULT 0,
  cash_out bigint NOT NULL DEFAULT 0,
  deposits bigint NOT NULL DEFAULT 0,
  net bigint NOT NULL DEFAULT 0,
  rake bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id, day)
);

-- 2. Indices
CREATE INDEX IF NOT EXISTS idx_club_wallet_tx_club_user_time ON public.club_wallet_transactions(club_id, user_id, created_at desc);
CREATE INDEX IF NOT EXISTS idx_club_wallet_tx_club_time ON public.club_wallet_transactions(club_id, created_at desc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_club_wallet_tx_idempotency ON public.club_wallet_transactions(club_id, user_id, currency, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_club_wallet_accounts_club_user ON public.club_wallet_accounts(club_id, user_id);
CREATE INDEX IF NOT EXISTS idx_club_daily_stats_club_day ON public.club_player_daily_stats(club_id, day desc);
CREATE INDEX IF NOT EXISTS idx_club_daily_stats_user_day ON public.club_player_daily_stats(user_id, day desc);

-- 3. Append-Only Trigger
CREATE OR REPLACE FUNCTION public.club_wallet_tx_append_only_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'club_wallet_transactions is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_club_wallet_tx_no_update ON public.club_wallet_transactions;
CREATE TRIGGER trg_club_wallet_tx_no_update
  BEFORE UPDATE OR DELETE ON public.club_wallet_transactions
  FOR EACH ROW EXECUTE FUNCTION public.club_wallet_tx_append_only_guard();

-- 4. RLS Policies
ALTER TABLE public.club_wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_wallet_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_player_daily_stats ENABLE ROW LEVEL SECURITY;

-- Service Role (Full Access)
DROP POLICY IF EXISTS club_wallet_tx_write_service ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_write_service ON public.club_wallet_transactions FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS club_wallet_accounts_write_service ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_write_service ON public.club_wallet_accounts FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS club_player_daily_stats_write_service ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_write_service ON public.club_player_daily_stats FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Authenticated Users (View Only)
DROP POLICY IF EXISTS club_wallet_tx_select ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_select ON public.club_wallet_transactions FOR SELECT TO authenticated
  USING (public.is_club_member(club_id) AND (user_id = auth.uid() OR public.is_club_admin(club_id)));

DROP POLICY IF EXISTS club_wallet_accounts_select ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_select ON public.club_wallet_accounts FOR SELECT TO authenticated
  USING (public.is_club_member(club_id) AND (user_id = auth.uid() OR public.is_club_admin(club_id)));

DROP POLICY IF EXISTS club_player_daily_stats_select ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_select ON public.club_player_daily_stats FOR SELECT TO authenticated
  USING (public.is_club_member(club_id));

-- 5. RPC Functions (Wallet Append)
CREATE OR REPLACE FUNCTION public.club_wallet_append_tx(
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
RETURNS table (
  tx_id uuid,
  current_balance bigint,
  created_at timestamptz,
  was_duplicate boolean
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  v_existing_id uuid;
  v_existing_created timestamptz;
  v_balance bigint;
  v_created timestamptz;
  v_buy_in_delta bigint := 0;
  v_cash_out_delta bigint := 0;
  v_deposit_delta bigint := 0;
BEGIN
  IF _amount = 0 THEN
    RAISE EXCEPTION 'wallet_tx_amount_must_be_non_zero';
  END IF;

  -- Idempotency Check
  IF _idempotency_key IS NOT NULL THEN
    SELECT id, created_at INTO v_existing_id, v_existing_created
    FROM public.club_wallet_transactions
    WHERE club_id = _club_id
      AND user_id = _user_id
      AND currency = _currency
      AND idempotency_key = _idempotency_key
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
      -- Ensure account exists to get balance
      INSERT INTO public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
      VALUES (_club_id, _user_id, _currency, 0, now())
      ON CONFLICT (club_id, user_id, currency) DO NOTHING;

      SELECT current_balance INTO v_balance
      FROM public.club_wallet_accounts
      WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency;

      RETURN QUERY SELECT v_existing_id, COALESCE(v_balance, 0), v_existing_created, true;
      RETURN;
    END IF;
  END IF;

  -- Lock & Balance Check
  INSERT INTO public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  VALUES (_club_id, _user_id, _currency, 0, now())
  ON CONFLICT (club_id, user_id, currency) DO NOTHING;

  SELECT current_balance INTO v_balance
  FROM public.club_wallet_accounts
  WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency
  FOR UPDATE;

  IF COALESCE(v_balance, 0) + _amount < 0 THEN
    RAISE EXCEPTION 'insufficient_wallet_balance';
  END IF;

  -- Insert Tx
  INSERT INTO public.club_wallet_transactions (
    club_id, user_id, type, amount, currency, ref_type, ref_id, created_by, note, meta_json, idempotency_key
  ) VALUES (
    _club_id, _user_id, _type, _amount, _currency, _ref_type, _ref_id, _created_by, _note, COALESCE(_meta_json, '{}'::jsonb), _idempotency_key
  ) RETURNING id, public.club_wallet_transactions.created_at INTO tx_id, v_created;

  -- Update Balance
  UPDATE public.club_wallet_accounts
  SET current_balance = COALESCE(current_balance, 0) + _amount,
      updated_at = now()
  WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency
  RETURNING current_balance INTO v_balance;

  -- Update Daily Stats
  IF _type = 'buy_in' THEN v_buy_in_delta := abs(_amount);
  ELSIF _type = 'cash_out' THEN v_cash_out_delta := abs(_amount);
  ELSIF _type IN ('deposit', 'admin_grant') AND _amount > 0 THEN v_deposit_delta := _amount;
  END IF;

  IF v_buy_in_delta <> 0 OR v_cash_out_delta <> 0 OR v_deposit_delta <> 0 THEN
    INSERT INTO public.club_player_daily_stats (club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake, updated_at)
    VALUES (_club_id, _user_id, now()::date, 0, v_buy_in_delta, v_cash_out_delta, v_deposit_delta, 0, 0, now())
    ON CONFLICT (club_id, user_id, day) DO UPDATE
    SET buy_in = public.club_player_daily_stats.buy_in + excluded.buy_in,
        cash_out = public.club_player_daily_stats.cash_out + excluded.cash_out,
        deposits = public.club_player_daily_stats.deposits + excluded.deposits,
        updated_at = now();
  END IF;

  RETURN QUERY SELECT tx_id, v_balance, v_created, false;
END;
$$;

-- 6. RPC Functions (Stats)
CREATE OR REPLACE FUNCTION public.club_record_hand_stats(
  _club_id uuid,
  _user_id uuid,
  _hands_delta integer,
  _net_delta bigint,
  _rake_delta bigint default 0
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
  INSERT INTO public.club_player_daily_stats (club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake, updated_at)
  VALUES (_club_id, _user_id, now()::date, COALESCE(_hands_delta, 0), 0, 0, 0, COALESCE(_net_delta, 0), COALESCE(_rake_delta, 0), now())
  ON CONFLICT (club_id, user_id, day) DO UPDATE
  SET hands = public.club_player_daily_stats.hands + excluded.hands,
      net = public.club_player_daily_stats.net + excluded.net,
      rake = public.club_player_daily_stats.rake + excluded.rake,
      updated_at = now();
END;
$$;

CREATE OR REPLACE FUNCTION public.club_get_leaderboard(
  _club_id uuid,
  _day_from date,
  _metric text default 'net',
  _limit integer default 50
)
RETURNS table (
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
LANGUAGE sql
STABLE
SECURITY INVOKER
AS $$
  WITH agg AS (
    SELECT
      s.club_id,
      s.user_id,
      sum(s.hands)::bigint as hands,
      sum(s.buy_in)::bigint as buy_in,
      sum(s.cash_out)::bigint as cash_out,
      sum(s.deposits)::bigint as deposits,
      sum(s.net)::bigint as net
    FROM public.club_player_daily_stats s
    WHERE s.club_id = _club_id
      AND s.day >= _day_from
    GROUP BY s.club_id, s.user_id
  ),
  scored AS (
    SELECT
      a.*,
      CASE
        WHEN _metric = 'hands' THEN a.hands
        WHEN _metric = 'buyin' THEN a.buy_in
        WHEN _metric = 'deposits' THEN a.deposits
        ELSE a.net
      END as metric_value
    FROM agg a
  ),
  ranked AS (
    SELECT
      row_number() OVER (ORDER BY s.metric_value DESC, s.user_id) as rank,
      s.club_id,
      s.user_id,
      s.metric_value,
      s.hands,
      s.buy_in,
      s.cash_out,
      s.deposits,
      s.net
    FROM scored s
  )
  SELECT
    r.rank::integer,
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
  FROM ranked r
  LEFT JOIN public.player_profiles pp ON pp.user_id = r.user_id
  WHERE r.rank <= greatest(1, least(coalesce(_limit, 50), 200));
$$;

-- 7. Permissions
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON TABLE public.club_wallet_transactions TO service_role;
GRANT ALL ON TABLE public.club_wallet_accounts TO service_role;
GRANT ALL ON TABLE public.club_player_daily_stats TO service_role;
GRANT EXECUTE ON FUNCTION public.club_wallet_append_tx TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_record_hand_stats TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_get_leaderboard TO service_role, authenticated;

COMMIT;

-- 8. Refresh Cache
NOTIFY pgrst, 'reload schema';
