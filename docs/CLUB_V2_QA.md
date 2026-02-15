# Club V2 — QA Checklist

## Milestone A: Persistence Layer

- [ ] **ClubRepo created** — `apps/game-server/src/services/club-repo.ts` implements full Supabase CRUD
- [ ] **ClubManager DB-backed** — `setRepo()` + `hydrate()` wired in `server.ts` at startup
- [ ] **Write-through on all mutations** — createClub, updateClub, requestJoin, approveJoin, rejectJoin, updateMemberRole, kickMember, banMember, unbanMember, createInvite, revokeInvite, createRuleset, updateRuleset, setDefaultRuleset, createTable, setTableRoomCode, closeTable, pauseTable
- [ ] **Audit log persisted** — `writeAudit()` calls `repo.appendAudit()` fire-and-forget
- [ ] **Hydration at startup** — clubs, members, invites, rulesets, tables loaded from DB into memory
- [ ] **Graceful offline** — server runs without Supabase (all repo methods are no-ops when `enabled()` is false)

## Milestone B: Security Gates

- [ ] **`join_room_code`** — club membership check at server.ts L1942-1946
- [ ] **`join_table`** — club membership check at server.ts L1994-2001
- [ ] **`sit_down`** — club membership check at server.ts L2046-2055
- [ ] **`seat_request`** — club membership check at server.ts L2146-2153
- [ ] **`requireActiveClubMember()` helper** — `services/club-service.ts` returns typed result with error codes
- [ ] **Pending members denied** — status=pending cannot join/sit/spectate
- [ ] **Banned members denied** — status=banned cannot join/sit/spectate
- [ ] **Left members denied** — status=left cannot join/sit/spectate
- [ ] **Error messages are clear** — "Club members only" / "Only active club members can sit"

## Milestone C: Club Table Isolation

- [ ] **Club tables always private** — created with `isPublic: false` and `visibility: "private"`
- [ ] **Global lobby filter** — `emitLobbySnapshot()` filters `room.status === "OPEN" && room.visibility === "public"`
- [ ] **Club tables never in public lobby** — verified by contract test in `club-manager.test.ts`
- [ ] **Club tables discoverable only via Club Detail → Tables tab**

## Milestone D: Club UX

- [ ] **"Clubs" nav entry** — appears in top nav bar (App.tsx)
- [ ] **My Clubs page** — lists clubs with badge, member count, table count
- [ ] **Create Club modal** — name, description, badge color, approval toggle
- [ ] **Join Club** — by club code or invite code
- [ ] **Club Detail — Overview tab** — description, visibility, approval, default ruleset
- [ ] **Club Detail — Members tab** — role badges, kick/ban (mod+), role change (admin+)
- [ ] **Club Detail — Tables tab** — create table (host+), join table, close table
- [ ] **Club Detail — Rulesets tab** — create/set default (admin+)
- [ ] **Club Detail — Invites tab** — create/revoke (mod+), copy invite code
- [ ] **Club Detail — Audit Log tab** — action history (mod+)
- [ ] **Pending join requests banner** — shown to mod+ with approve/reject buttons
- [ ] **Toast notifications** — club created, joined, approved, errors

## Milestone E: Rules-Driven Table Controls

- [ ] **preventDealMidHand=true enforced** — `startHandFlow()` throws "Hand in progress" if active
- [ ] **canPauseMidHand=false enforced** — pause deferred via `pendingPause` during active hand
- [ ] **pauseAppliesAfterHand=true enforced** — pause takes effect after hand ends
- [ ] **standUpAppliesAfterHand=true enforced** — stand-up deferred via `pendingStandUps` during active hand
- [ ] **Rule invariants enforced at creation** — `createRuleset()` forces preventDealMidHand=true, canPauseMidHand=false, pauseAppliesAfterHand=true
- [ ] **maxSeats clamped to 2–9** — enforced in createRuleset/updateRuleset

## No Monetization

- [ ] **rakeEnabled defaults to false** — in `DEFAULT_CLUB_RULES`
- [ ] **serviceFeeEnabled defaults to false** — in `DEFAULT_CLUB_RULES`
- [ ] **No payment UI** — no cashier, no real-money flows
- [ ] **Play-money disclaimer** — shown on ClubsPage and ClubDetailView

## Test Results

- [ ] **52 club-manager tests pass** (lifecycle, membership, permissions, rulesets, invites, tables, access enforcement, requireActiveClubMember, hydrate/persist, audit)
- [ ] **63 total game-server tests pass** (0 failures)
- [ ] **TypeScript compiles cleanly** (`tsc --noEmit` exits 0)

## Database Schema

- [ ] **`004_clubs_feature.sql`** — V1 simplified schema (clubs, club_members, club_ledger, live_tables.club_id)
- [ ] **`005_clubs.sql`** — Full production schema (clubs, club_members, club_invites, club_bans, club_rulesets, club_tables, club_audit_log + RLS policies)

## Files Changed

### New Files
- `apps/game-server/src/services/club-repo.ts` — Supabase persistence adapter (CRUD + bulk hydration)
- `apps/game-server/src/services/club-service.ts` — Business logic + `requireActiveClubMember()` gate
- `backend/sql/004_clubs_feature.sql` — V1 simplified club schema
- `docs/CLUB_V2_QA.md` — This QA checklist

### Modified Files
- `apps/game-server/src/club-manager.ts` — Added `setRepo()`, `hydrate()`, `persistCreateClub()`, write-through on all mutations, audit persistence
- `apps/game-server/src/server.ts` — Wired `ClubRepo` import + instantiation + hydration at startup
- `apps/game-server/src/__tests__/club-manager.test.ts` — Added 8 new tests (requireActiveClubMember gate + hydrate/persist interface)

### Pre-existing (no changes needed)
- `packages/shared-types/src/club-types.ts` — Full club type definitions + permission helpers
- `packages/shared-types/src/club-events.ts` — Socket event payloads + event maps
- `packages/shared-types/src/index.ts` — Already re-exports club types/events + LobbyRoomSummary has clubId/clubName
- `backend/sql/005_clubs.sql` — Full production schema with RLS
- `apps/game-server/src/server.ts` — Club socket handlers (L2985-3395), security gates on all join paths
- `apps/web/src/pages/clubs/ClubsPage.tsx` — My Clubs page + Create/Join modals
- `apps/web/src/pages/clubs/ClubDetailView.tsx` — Club detail with 6 tabs
- `apps/web/src/App.tsx` — Clubs nav, state management, socket event listeners
