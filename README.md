# CardPilot

Full-stack multiplayer poker training platform with GTO solver, AI bots, and coaching tools.

## Features

- **Multiplayer poker** — server-authoritative game engine with side pots, run-it-twice, bomb pots, double board
- **GTO Solver Workspace** — browser-based CFR solver with strategy browser, range editor, play mode
- **AI Bot System** — CFR-based decision pipeline with real-time subgame resolving (Pluribus-style)
- **Clubs** — create/join clubs with tables, credits, leaderboards, chat, analytics
- **Fast Battle** — speed poker mode for rapid GTO practice
- **Coaching Overlays** — real-time GTO advice, preflop charts, hand history review
- **Mobile Responsive** — adaptive UI with bottom tabs and touch support

## Repository Structure

```
apps/
  game-server/       Express + Socket.IO authoritative server
  bot-client/        AI poker bot with real-time resolver
  web/               React + Vite client (SPA)

packages/
  shared-types/      DTOs, socket events, type contracts
  game-engine/       Poker state machine, settlement, side pots
  poker-evaluator/   Hand evaluation, equity, board texture
  advice-engine/     GTO advice, line recognition, postflop engine
  cfr-solver/        CFR+ solver (vectorized), pipeline, value network
  fast-model/        Lightweight MLP for real-time inference
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## Prerequisites

- Node.js `>=24` (see `.nvmrc`)
- npm (workspace mode)

## Quick Start

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open `http://127.0.0.1:5173`

## Commands

```bash
npm run lint         # ESLint across all packages
npm run typecheck    # TypeScript check all workspaces
npm run test         # Unit tests (Node test runner + Vitest)
npm run build:web    # Vite production build
npm run build:server # Server TypeScript compile
npm run ci:verify    # Full CI pipeline locally
npm run env:doctor   # Environment health check
```

## Environment Variables

See `.env.example` for all available variables. Key ones:

| Variable                    | Description                               |
| --------------------------- | ----------------------------------------- |
| `PORT`                      | Server port (default: 4000)               |
| `VITE_SERVER_URL`           | Server URL for web client                 |
| `SUPABASE_URL`              | Supabase project URL (unset = guest mode) |
| `SUPABASE_ANON_KEY`         | Supabase publishable key                  |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key                 |
| `BOT_USE_RESOLVER`          | Enable real-time resolver in bot          |

When Supabase is not configured, the app runs in guest/local mode.

## Supabase Auth Setup (Google OAuth)

1. Create a Google OAuth client in [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Enable Google provider in Supabase dashboard (Authentication > Providers > Google)
3. Set Site URL and redirect URLs in Supabase (Authentication > URL Configuration)
4. Set environment variables: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

## CFR Training Data

Large training data is stored on IDrive E2 (not in Git):

```bash
npm run data:upload:v2
npm run data:download:v2
```

## Deployment

- **Web**: Netlify-compatible (`netlify.toml` included)
- **Server**: Railway/Node hosts (`PORT` env var respected)
- See `DEPLOY.md` and `docs/OPERATIONS.md` for details

## Trust & Safety

- Play-money only — not a real-money gambling platform
- `/privacy` and `/terms` available in the web app
- Vulnerability reporting: `SECURITY.md`

## Links

- [Architecture](docs/ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Operations](docs/OPERATIONS.md)
- [Solver Guide](docs/solver-integration-guide.md)
