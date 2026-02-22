DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'club_tables' AND column_name = 'config_json'
  ) THEN
    ALTER TABLE public.club_tables ADD COLUMN config_json jsonb NOT NULL DEFAULT '{}'::jsonb;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'club_tables' AND column_name = 'hands_played'
  ) THEN
    ALTER TABLE public.club_tables ADD COLUMN hands_played integer NOT NULL DEFAULT 0;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'club_tables' AND column_name = 'started_at'
  ) THEN
    ALTER TABLE public.club_tables ADD COLUMN started_at timestamptz;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'club_tables' AND column_name = 'finished_at'
  ) THEN
    ALTER TABLE public.club_tables ADD COLUMN finished_at timestamptz;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.check_constraints
    WHERE constraint_schema = 'public' AND constraint_name LIKE '%club_tables%status%'
  ) THEN
    BEGIN
      ALTER TABLE public.club_tables DROP CONSTRAINT IF EXISTS club_tables_status_check;
    EXCEPTION WHEN OTHERS THEN NULL;
    END;
  END IF;
END $$;
