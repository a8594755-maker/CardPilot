-- Debug wallet transaction
-- Run this in Supabase SQL Editor to test if the function works

-- Test 1: Check if we can call the function directly (as service role)
DO $$
DECLARE
  result RECORD;
  test_club_id uuid := '12345678-1234-1234-1234-123456789012'::uuid;
  test_user_id uuid := '87654321-4321-4321-4321-210987654321'::uuid;
BEGIN
  -- First check if clubs table has any clubs
  IF NOT EXISTS (SELECT 1 FROM public.clubs LIMIT 1) THEN
    RAISE NOTICE 'No clubs found in database. Create a club first via the app.';
  ELSE
    RAISE NOTICE 'Clubs exist in database.';
  END IF;
  
  -- Check if player_profiles has the user
  IF NOT EXISTS (SELECT 1 FROM public.player_profiles LIMIT 1) THEN
    RAISE NOTICE 'No player_profiles found. Users need to log in first.';
  ELSE
    RAISE NOTICE 'Player profiles exist.';
  END IF;
END $$;

-- Test 2: Check RLS policies
SELECT 
  schemaname,
  tablename,
  policyname,
  permissive,
  roles,
  cmd,
  qual
FROM pg_policies 
WHERE tablename IN ('club_wallet_transactions', 'club_wallet_accounts')
ORDER BY tablename, policyname;

-- Test 3: Try a direct insert test (this will fail if RLS blocks it)
-- Note: This should work if you're connected as service role
