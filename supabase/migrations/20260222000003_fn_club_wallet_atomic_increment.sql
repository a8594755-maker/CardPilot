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
