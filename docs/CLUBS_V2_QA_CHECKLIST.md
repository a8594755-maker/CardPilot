# Clubs V2 QA Checklist

## Part 0 — Persistence

- [ ] **Dev mode (no Supabase):** Start server without `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`. Server logs `ClubRepo running in offline mode` then `Using JSON file fallback for club persistence`. Clubs persist in `.data/clubs.json`.
- [ ] **Create club → restart server → club still in My Clubs** (JSON fallback).
- [ ] **Production (Supabase):** Server logs `ClubRepo connected to Supabase`. Clubs survive server restarts via DB hydration.
- [ ] `/healthz` returns `supabaseEnabled: true/false`.

## Part 1 — "My Clubs Disappears" Fix

- [ ] **Refresh page:** After creating a club, refresh the browser. Club still appears in My Clubs.
- [ ] **Reconnect socket:** Disconnect WiFi briefly, reconnect. My Clubs list repopulates automatically.
- [ ] **Navigate to Clubs tab:** Switching to Clubs tab triggers a fresh `club_list_my_clubs` fetch.
- [ ] **Refresh button:** Click "↻ Refresh" button in Clubs page header → clubs re-fetch. Button shows "Syncing…" while loading.
- [ ] **Loading skeleton:** When clubs are loading and list is empty, 3 animated skeleton cards appear.
- [ ] **Create club flow:** Create a new club → "Club created!" toast → club immediately appears in list.
- [ ] **Join club flow:** Enter club code → join → "Welcome to X!" toast → club appears in My Clubs.

## Part 2 — Clubs UX Upgrade

### Club Home (Overview Tab)

- [ ] Stats strip: Members, Online, Active Tables, Total Tables.
- [ ] Announcements section shows club description.
- [ ] Online members strip with role badges.
- [ ] Active tables with Quick Join button.
- [ ] Recent Activity preview (last 5 entries for admin+).
- [ ] Club info grid (visibility, approval, default ruleset, created date).

### Tables Tab

- [ ] List of tables with status badge (open/paused), player count, stakes, Join button.
- [ ] "Create Table" form for host+ with name input and **ruleset selector dropdown**.
- [ ] Close button for host+.
- [ ] Club tables do NOT appear in public lobby (verified by contract test).

### Members Tab

- [ ] Members sorted by role (owner → admin → host → mod → member).
- [ ] Online indicator (green dot) for recently active members.
- [ ] **Virtual credits balance** displayed per member (amber font).
- [ ] Admin actions: role select, **+$ grant credits** button, Kick, Ban.
- [ ] Grant credits: Click "+$" → prompt for amount → credits added, toast confirms.

### Rulesets Tab

- [ ] List existing rulesets with "DEFAULT" badge.
- [ ] **"+ New Ruleset"** button opens creation form.
- [ ] Form fields: name, SB, BB, seats, timer, buy-in min/max, time bank, run-it-twice, set-as-default.
- [ ] "Set as default" button on non-default rulesets.

### Invites Tab

- [ ] Create invite link (7-day expiry, 50 uses).
- [ ] Copy invite code to clipboard.
- [ ] Revoke invite.
- [ ] Used/max display.

### Activity Tab (admin+)

- [ ] Audit log with date, action type badge, description, actor.
- [ ] Color-coded action badges (join=green, ban/kick=red, table=cyan, role=purple).

### Settings Tab (admin+)

- [ ] Edit club name, description, badge color.
- [ ] Toggle "Require approval to join".
- [ ] Club code display with Copy button.
- [ ] "Save Settings" persists changes.

## Part 3 — Virtual Economy

- [ ] **Balance display:** Each member shows virtual credits balance in Members tab.
- [ ] **Grant credits (admin):** Admin clicks "+$" → enters amount → member balance updates.
- [ ] **Self add-on (admin/owner):** Admin/owner emits `club_request_addon` → auto-approved → balance increases.
- [ ] **Member add-on request:** Member emits `club_request_addon` → admins get `club_addon_request` notification.
- [ ] **Admin approves add-on:** Admin grants credits via `club_grant_credits` → member notified.
- [ ] **Deduct credits:** Admin can deduct credits from members (server-side only for now).
- [ ] **No real money:** Disclaimer visible on every club page ("play-money training tool").

## Test Results

- **Club manager tests:** 56/56 pass
- **Game engine tests:** 75/75 pass
- **TypeScript:** `tsc --noEmit` clean for both `apps/game-server` and `apps/web`

## Files Changed

### New Files

- `apps/game-server/src/services/club-repo-json.ts` — JSON file fallback persistence for dev mode

### Modified Files

- `packages/shared-types/src/club-types.ts` — Added `balance` field to `ClubMember`
- `apps/game-server/src/club-manager.ts` — Added `grantCredits`, `deductCredits`, `getMemberBalance`; balance in member creation
- `apps/game-server/src/services/club-repo.ts` — Added `balance` to `rowToMember`
- `apps/game-server/src/server.ts` — JSON fallback wiring; club_create logging; credit socket handlers
- `apps/game-server/src/__tests__/club-manager.test.ts` — 4 new persistence tests; path fix for lobby contract test
- `apps/web/src/App.tsx` — Emit `club_list_my_clubs` on connect; `clubsLoading` state; `onRefreshClubs` prop; `club_member_update` detail refresh
- `apps/web/src/pages/clubs/ClubsPage.tsx` — Loading skeleton; refresh button; `clubsLoading`/`onRefreshClubs` props
- `apps/web/src/pages/clubs/ClubDetailView.tsx` — Settings tab; ruleset creation form; table creation with ruleset selector; member balance display; grant credits UI
- `.gitignore` — Added `.data` directory
