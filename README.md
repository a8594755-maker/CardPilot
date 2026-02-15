# CardPilot

CardPilot is a multiplayer poker training product with a server-authoritative game loop, history review, and coaching overlays.

## Repository Structure
- `apps/game-server`: Express + Socket.IO authoritative server
- `apps/web`: React + Vite client
- `packages/game-engine`: poker hand state machine and settlement engine
- `packages/advice-engine`: strategy/advice helpers
- `packages/shared-types`: shared DTOs and contracts
- `backend/sql`: schema and Supabase migrations

## Prerequisites
- Node.js `>=20` (see `.nvmrc`)
- npm (workspace mode)

## Quick Start
1. Install dependencies:
```bash
npm install
```
2. Prepare environment:
```bash
cp .env.example .env.local
```
3. (Optional) Apply Supabase SQL migrations in order:
```sql
-- backend/sql/001_init.sql
-- backend/sql/002_supabase_multiplayer.sql
-- backend/sql/003_lobby_room_code.sql
-- backend/sql/004_hand_history_room_sessions.sql
```
4. Start web + server:
```bash
npm run dev
```
5. Open:
- `http://127.0.0.1:5173`

## Standard Commands
```bash
npm run lint
npm run typecheck
npm run test
npm run build:web
npm run build:server
npm run ci:verify
```

## Deployment Notes
- Web deploy is compatible with Netlify (`netlify.toml` is included).
- Server deploy can run on Railway/Node hosts (`PORT` respected).
- Use `docs/OPERATIONS.md` for runtime config, health checks, and shutdown behavior.

## Trust & Safety
- `/privacy` and `/terms` are available in the web app.
- CardPilot is explicitly play-money only and not a real-money gambling platform.
- Vulnerability reporting is documented in `SECURITY.md`.

## Governance & Maintenance
- Contribution guide: `CONTRIBUTING.md`
- Release discipline: `RELEASE.md`
- Change log: `CHANGELOG.md`
- Ownership: `.github/CODEOWNERS`

## Known Limitations
- No rake is applied in current settlement flows.
- Service reliability depends on Supabase availability when persistence is enabled.
- Some production controls (rate limiting, deeper observability) are still lightweight by design.
