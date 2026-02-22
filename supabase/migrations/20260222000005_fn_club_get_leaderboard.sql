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
  WHERE r.rank <= greatest(1, least(COALESCE(_limit, 50), 200))
$$;
