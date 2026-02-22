-- MASTER FIX SCRIPT for CardPilot Club System
-- Fixes: "Clubs being deleted" (Persistence) and "Club Credits not adding" (Wallet Permissions)
-- Run this in the Supabase SQL Editor.

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- 1. Ensure Tables Exist (Idempotent)
-- ═══════════════════════════════════════════════════════════════

-- A) Base Club Tables
CREATE TABLE IF NOT EXISTS public.clubs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(8) NOT NULL,
  name varchar(80) NOT NULL,
  description text NOT NULL DEFAULT '',
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  visibility varchar(16) NOT NULL DEFAULT 'private',
  default_ruleset_id uuid,
  is_archived boolean NOT NULL DEFAULT false,
  require_approval_to_join boolean NOT NULL DEFAULT true,
  badge_color varchar(7),
  logo_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.club_members (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role varchar(16) NOT NULL DEFAULT 'member',
  status varchar(16) NOT NULL DEFAULT 'active',
  nickname_in_club varchar(32),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.club_invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  invite_code varchar(16) NOT NULL,
  created_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  expires_at timestamptz,
  max_uses integer,
  uses_count integer NOT NULL DEFAULT 0,
  revoked boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.club_rulesets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  name varchar(80) NOT NULL,
  rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.club_tables (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  room_code varchar(12),
  name varchar(80) NOT NULL DEFAULT 'Club Table',
  ruleset_id uuid REFERENCES public.club_rulesets(id) ON DELETE SET NULL,
  status varchar(16) NOT NULL DEFAULT 'open',
  created_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.club_audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  actor_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  action_type varchar(40) NOT NULL,
  payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.club_bans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  reason text NOT NULL DEFAULT '',
  banned_by uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz
);

-- B) Wallet Tables
CREATE TABLE IF NOT EXISTS public.club_wallet_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type varchar(24) NOT NULL,
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

-- ═══════════════════════════════════════════════════════════════
-- 2. Indices (Ensure Performance)
-- ═══════════════════════════════════════════════════════════════
CREATE UNIQUE INDEX IF NOT EXISTS idx_clubs_code_unique ON public.clubs(code);
CREATE INDEX IF NOT EXISTS idx_club_members_user ON public.club_members(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_club_invites_code ON public.club_invites(invite_code);
CREATE UNIQUE INDEX IF NOT EXISTS idx_club_tables_room_code ON public.club_tables(room_code) WHERE room_code IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_club_wallet_tx_club_user_time ON public.club_wallet_transactions(club_id, user_id, created_at desc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_club_wallet_tx_idempotency ON public.club_wallet_transactions(club_id, user_id, currency, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- ═══════════════════════════════════════════════════════════════
-- 3. RLS Policies (CRITICAL FIX FOR PERMISSIONS)
-- ═══════════════════════════════════════════════════════════════

-- Enable RLS on all tables
ALTER TABLE public.clubs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_rulesets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_bans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_wallet_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_player_daily_stats ENABLE ROW LEVEL SECURITY;

-- Define Service Role Policies (FULL ACCESS)
-- This fixes the "Clubs being deleted" / "Credits not adding" if the server was blocked.

DO $$
DECLARE
  tbl text;
BEGIN
  FOR tbl IN
    SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE 'club%'
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_service_role_all ON public.%I', tbl, tbl);
    EXECUTE format('CREATE POLICY %I_service_role_all ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)', tbl, tbl);
  END LOOP;
  
  -- Also for clubs table specifically
  DROP POLICY IF EXISTS clubs_service_role_all ON public.clubs;
  CREATE POLICY clubs_service_role_all ON public.clubs FOR ALL TO service_role USING (true) WITH CHECK (true);
END
$$;

-- Define Authenticated Policies (READ ACCESS FIXES)

-- Clubs
DROP POLICY IF EXISTS clubs_select ON public.clubs;
CREATE POLICY clubs_select ON public.clubs FOR SELECT TO authenticated
  USING (visibility = 'unlisted' OR owner_user_id = auth.uid() OR EXISTS (
    SELECT 1 FROM public.club_members WHERE club_id = public.clubs.id AND user_id = auth.uid() AND status = 'active'
  ));

-- Members
DROP POLICY IF EXISTS club_members_select ON public.club_members;
CREATE POLICY club_members_select ON public.club_members FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR EXISTS (
    SELECT 1 FROM public.club_members cm WHERE cm.club_id = public.club_members.club_id AND cm.user_id = auth.uid() AND cm.status = 'active'
  ));

-- Wallet (View Own + Admin View All)
DROP POLICY IF EXISTS club_wallet_tx_select ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_select ON public.club_wallet_transactions FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.club_members cm 
      WHERE cm.club_id = public.club_wallet_transactions.club_id 
      AND cm.user_id = auth.uid() 
      AND cm.status = 'active'
      AND (public.club_wallet_transactions.user_id = auth.uid() OR cm.role IN ('owner', 'admin'))
    )
  );

-- ═══════════════════════════════════════════════════════════════
-- 4. RPC Functions (Wallet Logic)
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.club_wallet_append_tx(
  _club_id uuid,
  _user_id uuid,
  _type text,
  _amount bigint,
  _currency text DEFAULT 'chips',
  _ref_type text DEFAULT NULL,
  _ref_id text DEFAULT NULL,
  _created_by uuid DEFAULT NULL,
  _note text DEFAULT NULL,
  _meta_json jsonb DEFAULT '{}'::jsonb,
  _idempotency_key text DEFAULT NULL
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
  -- Idempotency Check
  IF _idempotency_key IS NOT NULL THEN
    SELECT id, created_at INTO v_existing_id, v_existing_created
    FROM public.club_wallet_transactions
    WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency AND idempotency_key = _idempotency_key
    LIMIT 1;
    IF v_existing_id IS NOT NULL THEN
       SELECT current_balance INTO v_balance FROM public.club_wallet_accounts WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency;
       RETURN QUERY SELECT v_existing_id, COALESCE(v_balance, 0), v_existing_created, true;
       RETURN;
    END IF;
  END IF;

  -- Upsert Account & Lock
  INSERT INTO public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  VALUES (_club_id, _user_id, _currency, 0, now())
  ON CONFLICT (club_id, user_id, currency) DO NOTHING;

  SELECT current_balance INTO v_balance
  FROM public.club_wallet_accounts
  WHERE club_id = _club_id AND user_id = _user_id AND currency = _currency
  FOR UPDATE;

  -- Balance Check
  IF COALESCE(v_balance, 0) + _amount < 0 THEN
    RAISE EXCEPTION 'insufficient_wallet_balance';
  END IF;

  -- Insert Tx
  INSERT INTO public.club_wallet_transactions (club_id, user_id, type, amount, currency, ref_type, ref_id, created_by, note, meta_json, idempotency_key)
  VALUES (_club_id, _user_id, _type, _amount, _currency, _ref_type, _ref_id, _created_by, _note, COALESCE(_meta_json, '{}'::jsonb), _idempotency_key)
  RETURNING id, public.club_wallet_transactions.created_at INTO tx_id, v_created;

  -- Update Balance
  UPDATE public.club_wallet_accounts
  SET current_balance = COALESCE(current_balance, 0) + _amount, updated_at = now()
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

-- ═══════════════════════════════════════════════════════════════
-- 5. Helper RPCs
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.increment_invite_uses(p_invite_id uuid)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
AS $$
  UPDATE public.club_invites
  SET uses_count = uses_count + 1
  WHERE id = p_invite_id;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5b. RLS helper functions
-- Drop first to allow parameter rename (p_club_id -> _club_id)
-- ═══════════════════════════════════════════════════════════════

DROP FUNCTION IF EXISTS public.is_club_member(uuid);
CREATE FUNCTION public.is_club_member(_club_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.club_members
    WHERE club_id = _club_id
      AND user_id = auth.uid()
      AND status = 'active'
  );
$$;

DROP FUNCTION IF EXISTS public.is_club_admin(uuid);
CREATE FUNCTION public.is_club_admin(_club_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.club_members
    WHERE club_id = _club_id
      AND user_id = auth.uid()
      AND status = 'active'
      AND role IN ('owner', 'admin')
  );
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5c. Atomic wallet balance increment (fallback for schema cache)
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.club_wallet_atomic_increment(
  _club_id uuid,
  _user_id uuid,
  _currency text,
  _delta bigint
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
  v_balance bigint;
BEGIN
  INSERT INTO public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  VALUES (_club_id, _user_id, _currency, 0, now())
  ON CONFLICT (club_id, user_id, currency) DO NOTHING;

  UPDATE public.club_wallet_accounts
  SET current_balance = current_balance + _delta,
      updated_at = now()
  WHERE club_id = _club_id
    AND user_id = _user_id
    AND currency = _currency
    AND current_balance + _delta >= 0
  RETURNING current_balance INTO v_balance;

  IF v_balance IS NULL THEN
    RAISE EXCEPTION 'insufficient_wallet_balance';
  END IF;

  RETURN v_balance;
END;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5d. Hand-end stats upsert
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.club_record_hand_stats(
  _club_id uuid,
  _user_id uuid,
  _hands_delta integer,
  _net_delta bigint,
  _rake_delta bigint DEFAULT 0
)
RETURNS void
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
BEGIN
  INSERT INTO public.club_player_daily_stats (
    club_id, user_id, day, hands, buy_in, cash_out, deposits, net, rake, updated_at
  )
  VALUES (
    _club_id, _user_id, now()::date,
    COALESCE(_hands_delta, 0), 0, 0, 0,
    COALESCE(_net_delta, 0), COALESCE(_rake_delta, 0), now()
  )
  ON CONFLICT (club_id, user_id, day) DO UPDATE
  SET hands = public.club_player_daily_stats.hands + EXCLUDED.hands,
      net = public.club_player_daily_stats.net + EXCLUDED.net,
      rake = public.club_player_daily_stats.rake + EXCLUDED.rake,
      updated_at = now();
END;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 5e. Leaderboard query RPC
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION public.club_get_leaderboard(
  _club_id uuid,
  _day_from date,
  _metric text DEFAULT 'net',
  _limit integer DEFAULT 50
)
RETURNS TABLE (
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
      sum(s.hands)::bigint AS hands,
      sum(s.buy_in)::bigint AS buy_in,
      sum(s.cash_out)::bigint AS cash_out,
      sum(s.deposits)::bigint AS deposits,
      sum(s.net)::bigint AS net
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
      END AS metric_value
    FROM agg a
  ),
  ranked AS (
    SELECT
      row_number() OVER (ORDER BY s.metric_value DESC, s.user_id) AS rank,
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
    _metric AS metric,
    r.metric_value,
    r.hands,
    r.buy_in,
    r.cash_out,
    r.deposits,
    r.net
  FROM ranked r
  LEFT JOIN public.player_profiles pp ON pp.user_id = r.user_id
  WHERE r.rank <= greatest(1, least(COALESCE(_limit, 50), 200));
$$;

-- ═══════════════════════════════════════════════════════════════
-- 6. Final Grants
-- ═══════════════════════════════════════════════════════════════
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;

GRANT EXECUTE ON FUNCTION public.club_wallet_append_tx TO authenticated;
GRANT EXECUTE ON FUNCTION public.club_wallet_atomic_increment TO authenticated;
GRANT EXECUTE ON FUNCTION public.club_record_hand_stats TO authenticated;
GRANT EXECUTE ON FUNCTION public.club_get_leaderboard TO authenticated;
GRANT EXECUTE ON FUNCTION public.increment_invite_uses TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_club_member TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_club_admin TO authenticated;

COMMIT;

NOTIFY pgrst, 'reload schema';
