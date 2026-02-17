# Club Wallet + Tables + Leaderboard

This document describes the club system invariants and runtime flow for wallet accounting, persistent tables, and leaderboard ranking.

## Scope

- Wallet balances are ledger-backed and auditable.
- Club cash tables are persistent/open and server-authoritative.
- Hands auto-run when enough eligible players are seated.
- Leave/stand-up during an active hand is deferred until hand end.
- Leaderboard metrics are reproducible from persisted aggregates.

## Core Data Model

### Wallet ledger

- `club_wallet_transactions`: append-only source of truth.
- `club_wallet_accounts`: cached per-user balance per currency.
- Write path: `club_wallet_append_tx(...)` (atomic ledger append + account update + stats side effects).

Supported wallet transaction types:
- `deposit`
- `admin_grant`
- `admin_deduct`
- `buy_in`
- `cash_out`
- `transfer_in`
- `transfer_out`
- `adjustment`

### Leaderboard stats

- `club_player_daily_stats`: per-day aggregates per player.
- `club_record_hand_stats(...)` updates hands/net/rake.
- `club_get_leaderboard(...)` returns ranked rows for a day/week/month window.

### Persistent club tables

- Club table metadata persists in `club_tables`.
- Room binding (`room_code`) is created and stored when needed.
- Table runtime settings are derived from ruleset JSON (including `minPlayersToStart`, `autoStartNextHand`, buy-in range, and variants).

## Non-Negotiable Runtime Invariants

1. `club_wallet_transactions` is immutable (append-only guard blocks update/delete).
2. Wallet balance cannot go below zero (enforced in atomic append function).
3. Idempotency is per wallet account (`club_id + user_id + currency + idempotency_key`).
4. Buy-in always debits wallet; stand-up/leave cash-out credits wallet for remaining stack.
5. Club tables are never auto-closed just because they are empty.
6. New hands start only when `eligiblePlayers >= minPlayersToStart`.
7. If eligible players drop below threshold, no new hand is started.
8. Leave/stand-up requests during an active hand are queued and applied only after the hand ends.
9. Deferred leave queue is flushed before scheduling next auto-deal.
10. Game progression is server-authoritative; clients only request actions.

## Permission Rules

- Owner/admin:
  - Can create/close/pause club tables.
  - Can execute wallet admin deposit/adjust.
- Members:
  - Can join club tables and play.
  - Can view own wallet and ledger.
  - Can view leaderboard.
- Non-members/pending/banned users are blocked by club gates on club table actions.

## Server Event Surface

Wallet:
- `club_wallet_balance_get`
- `club_wallet_transactions_list`
- `club_wallet_admin_deposit`
- `club_wallet_admin_adjust`

Leaderboard:
- `club_leaderboard_get`

Compatibility:
- `club_grant_credits` and `club_deduct_credits` are mapped to ledger-backed transactions.

## Verification Commands

Run from repo root:

```bash
npm run -w @cardpilot/shared-types typecheck
npm run -w @cardpilot/game-server typecheck
npm run -w @cardpilot/web typecheck
npm run -w @cardpilot/game-server test
```

These cover type contracts and wallet/table/leaderboard runtime tests.
