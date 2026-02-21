-- Ensure PostgREST can infer club_members -> player_profiles relationship.
-- This unblocks embedded selects like: club_members(*, player_profiles(display_name))

do $$
begin
  if to_regclass('public.club_members') is null or to_regclass('public.player_profiles') is null then
    raise notice 'Skipping FK migration: required tables missing.';
    return;
  end if;

  if not exists (
    select 1
    from pg_constraint
    where conname = 'club_members_user_id_player_profiles_fkey'
      and conrelid = 'public.club_members'::regclass
  ) then
    alter table public.club_members
      add constraint club_members_user_id_player_profiles_fkey
      foreign key (user_id) references public.player_profiles(user_id)
      on delete cascade
      not valid;
  end if;
end
$$;

notify pgrst, 'reload schema';
