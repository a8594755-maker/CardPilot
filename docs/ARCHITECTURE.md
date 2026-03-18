# CardPilot Architecture

## Monorepo Structure

```
CardPilot/
├── apps/
│   ├── game-server/     # Express + Socket.IO authoritative server
│   ├── bot-client/      # AI poker bot with CFR-based decision pipeline
│   └── web/             # React + Vite client (SPA)
├── packages/
│   ├── shared-types/    # DTOs, socket events, club/chat/notification types
│   ├── game-engine/     # Poker hand state machine, settlement, side pots
│   ├── poker-evaluator/ # Hand evaluation, equity calculation, board texture
│   ├── advice-engine/   # GTO advice, line recognition, postflop engine
│   ├── cfr-solver/      # CFR+ solver (vectorized), pipeline, value network
│   └── fast-model/      # Lightweight MLP for real-time strategy inference
├── data/                # Preflop charts, CFR solutions, training data
├── models/              # Trained value network weights (JSON)
├── scripts/             # Build, training, analysis scripts
└── docs/                # Documentation
```

## Package Dependency Graph

```
shared-types (leaf — no internal deps)
    ↑
poker-evaluator (depends on: shared-types)
    ↑
game-engine (depends on: poker-evaluator, shared-types)
    ↑
advice-engine (depends on: poker-evaluator, shared-types)
    ↑
cfr-solver (depends on: poker-evaluator, game-engine)
    ↑
fast-model (depends on: cfr-solver)
    ↑
game-server (depends on: game-engine, advice-engine, cfr-solver, poker-evaluator, shared-types)
bot-client (depends on: game-engine, advice-engine, cfr-solver, fast-model, poker-evaluator, shared-types)
web (depends on: shared-types, poker-evaluator)
```

## Core Systems

### 1. Game Engine (`packages/game-engine`)

- Server-authoritative poker state machine
- Supports: Hold'em (2-9 players), bomb pots, double board, run-it-twice/thrice
- Full side pot calculation with odd-chip rule
- Showdown with muck/reveal decision phase
- Sit out, time bank, auto-actions on timeout

### 2. Socket Communication

- Socket.IO with namespace separation:
  - Default `/` — game table operations (join, actions, lobby)
  - `/gto` — solver workspace WebSocket (solve jobs, progress)
  - `/clubs` — club management events
- Events defined in `packages/shared-types/src/socket-events.ts`
- Client reconnection with session restore

### 3. CFR Solver Pipeline (`packages/cfr-solver`)

- **Algorithm**: CFR+ with Chance-Sampled MCCFR
- **Vectorized engine**: Flat tree + ArrayStore for cache-friendly traversal
- **Pipeline**: 3-machine distributed solving
  - Queue Server (coordinator) — HTTP API for job management
  - Network Worker — polls queue, spawns fork() workers per board
  - Job Generator — enumerates 1,911 suit-isomorphic flops
- **Abstraction**: Dynamic bucket abstraction (50-100 buckets per street)
- **Output**: JSONL strategy files + meta.json per board

### 4. Value Network (`packages/fast-model`)

- Architecture: 54 → [256, 128] → action(3) + sizing(5)
- Input features: board texture, position, pot odds, SPR, street, etc.
- Trained on CFR solution data (200K iterations per board)
- Models: V2 (50bb SRP), V3 (100bb SRP)

### 5. Real-Time Resolver (`apps/bot-client/src/realtime-resolver.ts`)

- Pluribus-style subgame solving during live play
- Flow: Flop solve (1000 iter, cached) → Turn resolve (500 iter) → River resolve (300 iter)
- Uses value network as transition evaluation function at street boundaries

### 6. Bot Decision Pipeline (`apps/bot-client/src/decision.ts`)

- Tiered decision system:
  1. Preflop chart lookup
  2. Real-time resolver (if enabled)
  3. Advice engine (CFR lookup + value network)
  4. Monte Carlo simulation fallback
- Humanization: thinking time, mistake budget, mood, persona, opponent modeling

### 7. Solver Workspace (Web)

- Full GTO solver UI at `/solver`
- Features: board selection, range editor, tree configurator, live solve progress
- Strategy browser with 13x13 hand matrix visualization
- Play mode for practicing against solver solutions
- Database management for batch solving

### 8. Clubs System

- Full club management: create, invite, join with codes
- Per-club tables, credit system with ledger
- Roles: owner, admin, member
- Analytics, leaderboards, chat, audit log
- Club-scoped authentication gating

### 9. Fast Battle Mode

- Speed poker variant for rapid GTO practice
- Quick matchmaking with bot opponents
- Per-hand result feedback and session review

## Data Flow

### Live Game

```
Web Client → Socket.IO → game-server → game-engine (state machine)
                                     → advice-engine (GTO overlay)
                                     → Supabase (persistence, optional)
```

### Bot Play

```
game-server → Socket.IO → bot-client → decision pipeline
                                      → preflop-chart
                                      → realtime-resolver → cfr-solver (vectorized)
                                      → advice-engine → fast-model (value network)
                                      → monte-carlo (fallback)
```

### CFR Solving

```
job-generator → queue-server (HTTP) ← network-worker (polls)
                                    → fork() solve-worker per board
                                    → vectorized-cfr (200K iterations)
                                    → JSONL export + meta.json
```

## Environment Configuration

See `.env.example` at project root. Key variables:

| Variable                    | Required          | Description                               |
| --------------------------- | ----------------- | ----------------------------------------- |
| `PORT`                      | No (default 4000) | Server port                               |
| `CORS_ORIGIN`               | No                | Allowed CORS origins                      |
| `VITE_SERVER_URL`           | Yes               | Server URL for web client                 |
| `SUPABASE_URL`              | No                | Supabase project URL (unset = guest mode) |
| `SUPABASE_ANON_KEY`         | No                | Supabase anon key                         |
| `SUPABASE_SERVICE_ROLE_KEY` | No                | Supabase service role key                 |
| `BOT_USE_RESOLVER`          | No                | Enable real-time resolver in bot          |
| `DISABLE_SUPABASE`          | No                | Force guest/local mode                    |

## Build & Test

```bash
npm install          # Install all workspace dependencies
npm run lint         # ESLint across all packages
npm run typecheck    # TypeScript check all workspaces
npm run test         # Node test runner + Vitest
npm run build:web    # Vite production build
npm run build:server # Server TypeScript compile
npm run ci:verify    # Full CI pipeline locally
```
