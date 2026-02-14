# CardPilot MVP Blueprint

## 1. Product Defaults (for immediate start)
- Mode: Play-money training platform (no real money).
- Table type: 6-max cash.
- Advice timing: Real-time Coach Mode (only in training tables).
- Stack model: 100bb effective in MVP advice engine.
- Tech stack: Next.js (frontend) + NestJS (backend) + Socket.IO + PostgreSQL + Prisma.

## 2. State Machine (Hand Lifecycle)
- `WAITING_FOR_PLAYERS`
- `POST_BLINDS`
- `DEAL_HOLE`
- `BETTING_PREFLOP`
- `DEAL_FLOP`
- `BETTING_FLOP`
- `DEAL_TURN`
- `BETTING_TURN`
- `DEAL_RIVER`
- `BETTING_RIVER`
- `SHOWDOWN`
- `PAYOUT`
- `HAND_COMPLETE`

### Core hand state schema (server authoritative)
```json
{
  "handId": "uuid",
  "tableId": "uuid",
  "status": "BETTING_PREFLOP",
  "buttonSeat": 3,
  "smallBlind": 50,
  "bigBlind": 100,
  "deckSeedHash": "sha256:...",
  "board": [],
  "actorSeat": 5,
  "lastAggressorSeat": 2,
  "minRaiseTo": 300,
  "currentBet": 200,
  "pots": [{"amount": 450, "eligibleSeats": [1,2,5,6]}],
  "players": [
    {
      "seat": 1,
      "userId": "uuid",
      "stack": 9800,
      "inHand": true,
      "streetCommitted": 100,
      "hasActed": false,
      "isAllIn": false
    }
  ],
  "actions": []
}
```

## 3. Socket Events
### Client -> Server
- `join_table`: `{ tableId }`
- `leave_table`: `{ tableId }`
- `sit_down`: `{ tableId, seat, buyIn }`
- `stand_up`: `{ tableId, seat }`
- `action_submit`: `{ tableId, handId, action: "fold|check|call|raise", amount? }`
- `request_advice`: `{ tableId, handId }`

### Server -> Client
- `table_snapshot`
- `hand_started`
- `hole_cards` (private per player)
- `board_updated`
- `action_applied`
- `street_advanced`
- `advice_payload`
- `hand_ended`
- `error_event`

### Payload examples
```json
{
  "event": "action_applied",
  "data": {
    "tableId": "t1",
    "handId": "h1",
    "seat": 5,
    "action": "raise",
    "amount": 300,
    "nextActorSeat": 6,
    "potTotal": 650
  }
}
```

```json
{
  "event": "advice_payload",
  "data": {
    "tableId": "t1",
    "handId": "h1",
    "seat": 6,
    "spotKey": "6max_cash_100bb_BTN_vs_BB_unopened_open2.5x",
    "heroHand": "A5s",
    "mix": {"raise": 0.65, "call": 0.0, "fold": 0.35},
    "tags": ["IP_ADVANTAGE", "A_BLOCKER", "WHEEL_PLAYABILITY"],
    "explanation": "Button has positional edge. A5s blocks strong Ax continues and keeps playable wheel potential."
  }
}
```

## 4. Preflop Advice Key Spec
Use deterministic key format:

`{format}_{players}_{stack}_{heroPos}_vs_{villainPos}_{line}_{size}`

Examples:
- `cash_6max_100bb_BTN_vs_BB_unopened_open2.5x`
- `cash_6max_100bb_BB_vs_BTN_facing_open2.5x`
- `cash_6max_100bb_BTN_vs_BB_facing_3bet9x`

### Columns to store
- `format`: `cash`
- `players`: `6max`
- `effective_stack_bb`: `100`
- `hero_pos`: `BTN`
- `villain_pos`: `BB`
- `line`: `unopened|facing_open|facing_3bet|facing_4bet`
- `size_bucket`: `open2.5x|3bet9x|4bet22x`
- `hand_code`: `A5s`
- `raise_freq`, `call_freq`, `fold_freq`
- `reason_tags`: string array

## 5. Folder Structure (recommended)
```txt
CardPilot/
  apps/
    web/                  # Next.js table UI
    game-server/          # NestJS + Socket.IO
  packages/
    game-engine/          # Pure state machine + rules
    advice-engine/        # Preflop chart query + explanation templates
    shared-types/         # DTOs/events/schemas
  backend/
    sql/                  # SQL migrations (bootstrap only)
  docs/
    mvp-blueprint.md
```

## 6. Execution Plan (first 10 working sessions)
1. Create monorepo scaffolding and shared event DTOs.
2. Build room lifecycle: create/join/sit/stand + snapshot sync.
3. Implement preflop-only game engine with rule validation.
4. Persist hands + actions + seat snapshots to PostgreSQL.
5. Wire frontend table view to server events.
6. Add preflop chart table + lookup API.
7. Push `advice_payload` on hero turn in training tables.
8. Add hand end settlement and basic showdown evaluator.
9. Add reconnect flow (`table_snapshot` + in-flight hand recovery).
10. Add CI checks and basic load test for 10 concurrent tables.
