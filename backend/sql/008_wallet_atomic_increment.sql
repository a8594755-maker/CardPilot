-- Atomic wallet balance increment helper
-- Used as fallback when club_wallet_append_tx RPC is unavailable (schema cache)
-- Run after 007_club_wallet_and_leaderboard.sql

create or replace function public.club_wallet_atomic_increment(
  _club_id uuid,
  _user_id uuid,
  _currency text,
  _delta bigint
)
returns bigint
language plpgsql
security invoker
as $$
declare
  v_balance bigint;
begin
  -- Ensure row exists
  insert into public.club_wallet_accounts (club_id, user_id, currency, current_balance, updated_at)
  values (_club_id, _user_id, _currency, 0, now())
  on conflict (club_id, user_id, currency) do nothing;

  -- Atomic locked update with insufficient-funds guard
  update public.club_wallet_accounts
  set current_balance = current_balance + _delta,
      updated_at = now()
  where club_id = _club_id
    and user_id = _user_id
    and currency = _currency
    and current_balance + _delta >= 0
  returning current_balance into v_balance;

  if v_balance is null then
    raise exception 'insufficient_wallet_balance';
  end if;

  return v_balance;
end;
$$;

NOTIFY pgrst, 'reload schema';
