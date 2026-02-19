-- Fix all Supabase schema issues

-- ═══════════════════════════════════════════════════════════════
-- 1. Refresh schema cache (notify PostgREST to reload)
-- ═══════════════════════════════════════════════════════════════
NOTIFY pgrst, 'reload schema';

-- ═══════════════════════════════════════════════════════════════
-- 2. Fix player_profiles RLS policy
-- ═══════════════════════════════════════════════════════════════
DROP POLICY IF EXISTS player_profiles_write_service_role ON public.player_profiles;
CREATE POLICY player_profiles_write_service_role
  ON public.player_profiles
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 3. Create live_tables if missing (and add room_code)
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS public.live_tables (
  id text PRIMARY KEY,
  status varchar(16) NOT NULL DEFAULT 'OPEN',
  max_players smallint NOT NULL DEFAULT 6,
  room_code varchar(12),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.live_table_seats (
  table_id text NOT NULL REFERENCES public.live_tables(id) ON DELETE CASCADE,
  seat_no smallint NOT NULL CHECK (seat_no BETWEEN 1 AND 9),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  display_name varchar(32) NOT NULL,
  stack integer NOT NULL CHECK (stack >= 0),
  is_connected boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (table_id, seat_no),
  UNIQUE (table_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.live_table_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  table_id text NOT NULL REFERENCES public.live_tables(id) ON DELETE CASCADE,
  hand_id text,
  event_type varchar(40) NOT NULL,
  actor_user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_live_table_events_table_time ON public.live_table_events(table_id, created_at desc);

-- Enable RLS for live tables
ALTER TABLE public.live_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_table_seats ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.live_table_events ENABLE ROW LEVEL SECURITY;

-- Policies for live tables
DROP POLICY IF EXISTS live_tables_select_authenticated ON public.live_tables;
CREATE POLICY live_tables_select_authenticated ON public.live_tables FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS live_tables_write_service_role ON public.live_tables;
CREATE POLICY live_tables_write_service_role ON public.live_tables FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS live_table_seats_select_authenticated ON public.live_table_seats;
CREATE POLICY live_table_seats_select_authenticated ON public.live_table_seats FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS live_table_seats_write_service_role ON public.live_table_seats;
CREATE POLICY live_table_seats_write_service_role ON public.live_table_seats FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS live_table_events_select_authenticated ON public.live_table_events;
CREATE POLICY live_table_events_select_authenticated ON public.live_table_events FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS live_table_events_write_service_role ON public.live_table_events;
CREATE POLICY live_table_events_write_service_role ON public.live_table_events FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 4. Ensure all club tables exist with correct structure
-- ═══════════════════════════════════════════════════════════════

-- clubs
CREATE TABLE IF NOT EXISTS public.clubs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(8) NOT NULL,
  name varchar(80) NOT NULL,
  description text NOT NULL DEFAULT '',
  owner_user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  visibility varchar(16) NOT NULL DEFAULT 'private' CHECK (visibility IN ('private', 'unlisted')),
  default_ruleset_id uuid,
  is_archived boolean NOT NULL DEFAULT false,
  require_approval_to_join boolean NOT NULL DEFAULT true,
  badge_color varchar(7),
  logo_url text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clubs_code_unique ON public.clubs(code);

-- club_members
CREATE TABLE IF NOT EXISTS public.club_members (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role varchar(16) NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'host', 'mod', 'member')),
  status varchar(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'pending', 'banned', 'left')),
  nickname_in_club varchar(32),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id)
);

-- club_wallet_accounts (if not exists)
CREATE TABLE IF NOT EXISTS public.club_wallet_accounts (
  club_id uuid NOT NULL REFERENCES public.clubs(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  currency varchar(16) NOT NULL DEFAULT 'chips',
  current_balance bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (club_id, user_id, currency)
);

-- club_wallet_transactions (if not exists)
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

-- club_player_daily_stats (if not exists)
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
-- 5. Fix all RLS policies to use service_role correctly
-- ═══════════════════════════════════════════════════════════════

-- Enable RLS
ALTER TABLE public.clubs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_wallet_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_wallet_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.club_player_daily_stats ENABLE ROW LEVEL SECURITY;

-- Fix club tables write policies
DO $$
DECLARE
  tables text[] := ARRAY['clubs', 'club_members', 'club_invites', 'club_bans', 'club_rulesets', 'club_tables', 'club_audit_log'];
  t text;
BEGIN
  FOREACH t IN ARRAY tables
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS %I_write_service ON public.%I', t, t);
    EXECUTE format('CREATE POLICY %I_write_service ON public.%I FOR ALL TO service_role USING (true) WITH CHECK (true)', t, t);
  END LOOP;
END $$;

-- Fix wallet tables write policies
DROP POLICY IF EXISTS club_wallet_tx_write_service ON public.club_wallet_transactions;
CREATE POLICY club_wallet_tx_write_service ON public.club_wallet_transactions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS club_wallet_accounts_write_service ON public.club_wallet_accounts;
CREATE POLICY club_wallet_accounts_write_service ON public.club_wallet_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS club_player_daily_stats_write_service ON public.club_player_daily_stats;
CREATE POLICY club_player_daily_stats_write_service ON public.club_player_daily_stats
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ═══════════════════════════════════════════════════════════════
-- 6. Refresh schema cache again
-- ═══════════════════════════════════════════════════════════════
NOTIFY pgrst, 'reload schema';

SELECT 'Schema fix complete' as status;
