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
