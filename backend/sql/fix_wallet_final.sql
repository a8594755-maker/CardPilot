-- Fix wallet tables - final version

-- ═══════════════════════════════════════════════════════════════
-- 1. wallet transactions
-- ═══════════════════════════════════════════════════════════════
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

CREATE INDEX IF NOT EXISTS idx_club_wallet_tx_club_user_time ON public.club_wallet_transactions(club_id, user_id, created_at desc);
CREATE INDEX IF NOT EXISTS idx_club_wallet_tx_club_time ON public.club_wallet_transactions(club_id, created_at desc);
CREATE UNIQUE INDEX IF NOT EXISTS idx_club_wallet_tx_idempotency ON public.club_wallet_transactions(club_id, user_id, currency, idempotency_key) WHERE idempotency_key IS NOT NULL;

-- Trigger to prevent update/delete
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

ALTER TABLE public.club_wallet_transactions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS club_wallet_tx_select ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_select ON public.club_wallet_transactions
  FOR SELECT TO authenticated
  USING (public.is_club_member(club_id) AND (user_id = auth.uid() OR public.is_club_admin(club_id)));

DROP POLICY IF EXISTS club_wallet_tx_write_service ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_write_service ON public.club_wallet_transactions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 2. wallet accounts
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS public.club_wallet_accounts (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  currency varchar(16) NOT NULL DEFAULT 'chips',
  current_balance bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id, currency)
);

CREATE INDEX IF NOT EXISTS idx_club_wallet_accounts_club_user ON public.club_wallet_accounts(club_id, user_id);

ALTER TABLE public.club_wallet_accounts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS club_wallet_accounts_select ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_select ON public.club_wallet_accounts
  FOR SELECT TO authenticated
  USING (public.is_club_member(club_id) AND (user_id = auth.uid() OR public.is_club_admin(club_id)));

DROP POLICY IF EXISTS club_wallet_accounts_write_service ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_write_service ON public.club_wallet_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 3. daily stats
-- ═══════════════════════════════════════════════════════════════
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

CREATE INDEX IF NOT EXISTS idx_club_daily_stats_club_day ON public.club_player_daily_stats(club_id, day desc);
CREATE INDEX IF NOT EXISTS idx_club_daily_stats_user_day ON public.club_player_daily_stats(user_id, day desc);

ALTER TABLE public.club_player_daily_stats ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS club_player_daily_stats_select ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_select ON public.club_player_daily_stats
  FOR SELECT TO authenticated USING (public.is_club_member(club_id));

DROP POLICY IF EXISTS club_player_daily_stats_write_service ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_write_service ON public.club_player_daily_stats
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 4. Refresh schema cache
-- ═══════════════════════════════════════════════════════════════
NOTIFY pgrst, 'reload schema';

SELECT 'Wallet tables fixed' as status;
