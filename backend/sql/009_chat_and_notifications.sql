-- Chat & Notification system schema
-- Run after 008_wallet_atomic_increment.sql

-- ═══════════════════════════════════════════════════════════════
-- 1) chat_messages
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  table_id uuid references public.club_tables(id) on delete set null,
  sender_user_id uuid not null references auth.users(id) on delete cascade,
  sender_display_name varchar(80) not null default '',
  message_type varchar(16) not null default 'text' check (message_type in ('text', 'system')),
  content text not null,
  mentions jsonb not null default '[]'::jsonb,
  deleted_at timestamptz,
  deleted_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now()
);

create index if not exists idx_chat_messages_club_time
  on public.chat_messages(club_id, created_at desc);

create index if not exists idx_chat_messages_club_table_time
  on public.chat_messages(club_id, table_id, created_at desc)
  where table_id is not null;

create index if not exists idx_chat_messages_mentions
  on public.chat_messages using gin (mentions);

-- ═══════════════════════════════════════════════════════════════
-- 2) chat_mutes
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.chat_mutes (
  id uuid primary key default gen_random_uuid(),
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  muted_by uuid not null references auth.users(id) on delete cascade,
  reason text not null default '',
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  unique (club_id, user_id)
);

create index if not exists idx_chat_mutes_club_user
  on public.chat_mutes(club_id, user_id);

-- ═══════════════════════════════════════════════════════════════
-- 3) chat_read_cursors
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.chat_read_cursors (
  club_id uuid not null references public.clubs(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  scope_key varchar(80) not null default 'club',
  last_read_message_id uuid references public.chat_messages(id) on delete set null,
  last_read_at timestamptz not null default now(),
  primary key (club_id, user_id, scope_key)
);

-- ═══════════════════════════════════════════════════════════════
-- 4) notifications
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  type varchar(32) not null check (
    type in (
      'table_opened',
      'table_started',
      'join_request_received',
      'join_request_approved',
      'join_request_rejected',
      'role_changed',
      'kicked',
      'banned',
      'credit_granted',
      'credit_deducted',
      'chat_mention'
    )
  ),
  club_id uuid references public.clubs(id) on delete cascade,
  ref_id text,
  title varchar(200) not null,
  body text not null default '',
  metadata jsonb not null default '{}'::jsonb,
  is_read boolean not null default false,
  read_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists idx_notifications_user_unread_time
  on public.notifications(user_id, is_read, created_at desc);

create index if not exists idx_notifications_user_time
  on public.notifications(user_id, created_at desc);

-- ═══════════════════════════════════════════════════════════════
-- 5) notification_preferences
-- ═══════════════════════════════════════════════════════════════

create table if not exists public.notification_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  preferences jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- ═══════════════════════════════════════════════════════════════
-- RLS
-- ═══════════════════════════════════════════════════════════════

alter table public.chat_messages enable row level security;
alter table public.chat_mutes enable row level security;
alter table public.chat_read_cursors enable row level security;
alter table public.notifications enable row level security;
alter table public.notification_preferences enable row level security;

-- ── chat_messages ──
drop policy if exists chat_messages_select on public.chat_messages;
create policy chat_messages_select on public.chat_messages
  for select to authenticated
  using (public.is_club_member(club_id));

drop policy if exists chat_messages_service_role_all on public.chat_messages;
create policy chat_messages_service_role_all on public.chat_messages
  for all to service_role
  using (true)
  with check (true);

-- ── chat_mutes ──
drop policy if exists chat_mutes_select on public.chat_mutes;
create policy chat_mutes_select on public.chat_mutes
  for select to authenticated
  using (
    user_id = auth.uid()
    or public.is_club_admin(club_id)
  );

drop policy if exists chat_mutes_service_role_all on public.chat_mutes;
create policy chat_mutes_service_role_all on public.chat_mutes
  for all to service_role
  using (true)
  with check (true);

-- ── chat_read_cursors ──
drop policy if exists chat_read_cursors_select on public.chat_read_cursors;
create policy chat_read_cursors_select on public.chat_read_cursors
  for select to authenticated
  using (user_id = auth.uid());

drop policy if exists chat_read_cursors_upsert on public.chat_read_cursors;
create policy chat_read_cursors_upsert on public.chat_read_cursors
  for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists chat_read_cursors_service_role_all on public.chat_read_cursors;
create policy chat_read_cursors_service_role_all on public.chat_read_cursors
  for all to service_role
  using (true)
  with check (true);

-- ── notifications ──
drop policy if exists notifications_select on public.notifications;
create policy notifications_select on public.notifications
  for select to authenticated
  using (user_id = auth.uid());

drop policy if exists notifications_update on public.notifications;
create policy notifications_update on public.notifications
  for update to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists notifications_service_role_all on public.notifications;
create policy notifications_service_role_all on public.notifications
  for all to service_role
  using (true)
  with check (true);

-- ── notification_preferences ──
drop policy if exists notification_preferences_select on public.notification_preferences;
create policy notification_preferences_select on public.notification_preferences
  for select to authenticated
  using (user_id = auth.uid());

drop policy if exists notification_preferences_upsert on public.notification_preferences;
create policy notification_preferences_upsert on public.notification_preferences
  for all to authenticated
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

drop policy if exists notification_preferences_service_role_all on public.notification_preferences;
create policy notification_preferences_service_role_all on public.notification_preferences
  for all to service_role
  using (true)
  with check (true);

-- ═══════════════════════════════════════════════════════════════
-- GRANTS
-- ═══════════════════════════════════════════════════════════════

grant all on table public.chat_messages to service_role;
grant all on table public.chat_mutes to service_role;
grant all on table public.chat_read_cursors to service_role;
grant all on table public.notifications to service_role;
grant all on table public.notification_preferences to service_role;

grant select on table public.chat_messages to authenticated;
grant select on table public.chat_mutes to authenticated;
grant select, insert, update on table public.chat_read_cursors to authenticated;
grant select, update on table public.notifications to authenticated;
grant select, insert, update on table public.notification_preferences to authenticated;
