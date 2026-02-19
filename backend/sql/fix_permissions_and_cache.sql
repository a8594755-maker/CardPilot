-- Fix permissions and schema cache for Club Wallet
-- Run this in the Supabase SQL Editor to resolve "function not found" and permission errors.

-- 1. Reload schema cache (critical for RPC visibility)
NOTIFY pgrst, 'reload schema';

-- 2. Grant usage on schema public to roles
GRANT USAGE ON SCHEMA public TO postgres, anon, authenticated, service_role;

-- 3. Grant permissions on tables
GRANT ALL ON TABLE public.club_wallet_transactions TO service_role;
GRANT ALL ON TABLE public.club_wallet_accounts TO service_role;
GRANT ALL ON TABLE public.club_player_daily_stats TO service_role;

-- Allow authenticated users to view their own data (RLS will handle row filtering)
GRANT SELECT ON TABLE public.club_wallet_transactions TO authenticated;
GRANT SELECT ON TABLE public.club_wallet_accounts TO authenticated;
GRANT SELECT ON TABLE public.club_player_daily_stats TO authenticated;

-- 4. Grant execute on RPC functions
GRANT EXECUTE ON FUNCTION public.club_wallet_append_tx TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_record_hand_stats TO service_role, authenticated;
GRANT EXECUTE ON FUNCTION public.club_get_leaderboard TO service_role, authenticated;

-- 5. Ensure RLS policies exist and are correct for service_role
-- (Re-applying just in case to ensure write access)

-- Wallet Transactions
DROP POLICY IF EXISTS club_wallet_tx_write_service ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_write_service ON public.club_wallet_transactions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Wallet Accounts
DROP POLICY IF EXISTS club_wallet_accounts_write_service ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_write_service ON public.club_wallet_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Daily Stats
DROP POLICY IF EXISTS club_player_daily_stats_write_service ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_write_service ON public.club_player_daily_stats
  FOR ALL TO service_role USING (true) WITH CHECK (true);

SELECT 'Permissions fixed and schema cache reload notified' as status;
