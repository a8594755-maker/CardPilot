# Club System E2E QA

Date: 2026-02-17

## Prerequisites
- Run game server and web app.
- Sign in with at least three users:
  - `owner_admin` (owner/admin role)
  - `member_a` (active member)
  - `member_b` (active member)

## Scenario 1: Owner creates multiple persistent tables with different rulesets
1. As owner/admin, open Clubs and select a club.
2. Create two rulesets with different blinds, seats, and buy-in limits.
3. Create two tables, one per ruleset.
4. Refresh club detail.
Expected:
- Both tables are listed.
- Each table shows its own stakes/seats configuration.
- No hard table count cap blocks creation.

## Scenario 2: Member sees simplified club UI only
1. As `member_a`, open the same club.
Expected:
- Visible sections are limited to table list, balance, and leaderboard.
- Leaderboard defaults to `Last 7 days` with scope switcher for `Last 24h` / `Last 7d` / `All-time`.
- No members/rulesets/invites/audit/settings/admin controls.
- No `+ New Table` and no `Close` buttons.
- No `host`/`mod` role labels or role controls are shown anywhere.

## Scenario 3: Admin-only route sanitization
1. Navigate directly to `/clubs/admin` or `/clubs/<clubId>/settings`.
Expected:
- Client redirects to `/clubs`.
- No admin controls render for non-admin users.

## Scenario 4: Instant sit for club members
1. As `member_a`, click Join on a club table and pick seat/buy-in.
Expected:
- Seat is taken immediately.
- No host approval panel or pending seat request path is required.

## Scenario 5: Auto-deal hostless runtime
1. Seat `member_a` and `member_b` at the same club table.
Expected:
- Hand auto-starts once minimum active seated players is met.
- Next hands continue automatically.
2. Stand one player up so active seated players < 2.
Expected:
- New hands stop.
- UI shows waiting-for-players state.

## Scenario 6: Leave/stand during hand is deferred
1. While a hand is active, click Stand/Leave as a seated player.
Expected:
- UI shows pending leave-after-hand state.
- Seat remains until hand ends.
- Stand/leave executes only after hand completion.

## Scenario 7: Runtime remains open when empty
1. Make all players leave/stand from a club table.
Expected:
- Runtime room does not auto-close when seated count reaches 0.
- Table still appears in club table list.
2. Rejoin the same table.
Expected:
- Join works immediately without manual reopen.
- Table status stays open and waits for players.

## Scenario 8: Update table ruleset association
1. As owner/admin, edit table (name and/or ruleset).
Expected:
- Update is rejected if a hand is active.
- Update is rejected if new max seats is below occupied seat count.
- On success, room metadata/settings and snapshot reflect new table rules.

## Scenario 9: Credits ledger and leaderboard refresh
1. As owner/admin, grant and deduct credits for `member_a`.
Expected:
- Ledger entries are append-only with actor and reason.
- Member balance updates immediately.
- Last-7-days leaderboard refreshes without polling.
2. Play a hand and finish settlement.
Expected:
- Leaderboard net values update after settlement.
