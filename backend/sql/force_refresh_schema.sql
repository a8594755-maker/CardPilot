-- Force schema cache reload
-- This is necessary when Supabase/PostgREST doesn't pick up table creation changes immediately.
-- Run this in the Supabase SQL Editor.

NOTIFY pgrst, 'reload schema';

-- Verify the table exists
SELECT to_regclass('public.club_wallet_transactions') as table_exists;
