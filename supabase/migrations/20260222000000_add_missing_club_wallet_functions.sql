-- Add missing Club Wallet RPC functions
-- Fixes: "Could not find function public.club_wallet_atomic_increment in the schema cache"
-- Also adds: club_record_hand_stats, club_get_leaderboard, is_club_member, is_club_admin

BEGIN;

-- ═══════════════════════════════════════════════════════════════
-- 1. Helper functions for RLS policies
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
-- 2. Atomic wallet balance increment (fallback for schema cache issues)
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
  -- Ensure row exists
  INSERT INTO public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  VALUES (_club_id, _user_id, _currency, 0, now())
  ON CONFLICT (club_id, user_id, currency) DO NOTHING;

  -- Atomic locked update with insufficient-funds guard
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
-- 3. Hand-end stats upsert (hands + net + rake)
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
    _club_id,
    _user_id,
    now()::date,
    COALESCE(_hands_delta, 0),
    0,
    0,
    0,
    COALESCE(_net_delta, 0),
    COALESCE(_rake_delta, 0),
    now()
  )
  ON CONFLICT (club_id, user_id, day) DO UPDATE
  SET hands = public.club_player_daily_stats.hands + EXCLUDED.hands,
      net = public.club_player_daily_stats.net + EXCLUDED.net,
      rake = public.club_player_daily_stats.rake + EXCLUDED.rake,
      updated_at = now();
END;
$$;

-- ═══════════════════════════════════════════════════════════════
-- 4. Leaderboard query RPC
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
-- 5. Grants
-- ═══════════════════════════════════════════════════════════════

GRANT EXECUTE ON FUNCTION public.club_wallet_atomic_increment TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_record_hand_stats TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_get_leaderboard TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.is_club_member TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.is_club_admin TO service_role, authenticated;

COMMIT;

-- Force PostgREST schema cache reload
NOTIFY pgrst, 'reload schema';
