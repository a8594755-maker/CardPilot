# CardPilot MVP

Texas Hold'em training platform scaffold with real-time table sync and preflop GTO advice.

## Included
- `apps/game-server`: Express + Socket.IO server (server-authoritative game loop)
- `apps/web`: React + Vite table client
- `packages/game-engine`: hand state machine, betting flow, showdown
- `packages/advice-engine`: preflop chart lookup + explanation tags
- `packages/shared-types`: shared event/state DTOs
- `backend/sql/001_init.sql`: PostgreSQL schema
- `backend/sql/002_supabase_multiplayer.sql`: Supabase multiplayer persistence tables + RLS
- `backend/sql/003_lobby_room_code.sql`: room code + lobby fields and indexes
- `docs/mvp-blueprint.md`: product + architecture blueprint

## Run locally
1. Create env file:
```bash
cp .env.example .env.local
```
2. Install dependencies:
```bash
npm install
```
3. (Optional but recommended) In Supabase SQL Editor, run:
```sql
-- backend/sql/002_supabase_multiplayer.sql
-- backend/sql/003_lobby_room_code.sql
```
4. Start web + server together:
```bash
npm run dev
```
5. Open client:
- `http://127.0.0.1:5173`

## Basic flow
1. Open two browser tabs.
2. Create a room in `大廳` to get a shareable room code.
3. In another tab, join with the same room code.
4. Sit in different seats.
5. Click `開始手牌`.
6. Take actions and observe `GTO Advice` panel on active seat.

## Notes
- Current engine supports full streets and showdown.
- Side pots are not fully implemented yet; avoid uneven all-in stacks for now.
- Preflop advice uses `data/preflop_charts.sample.json` + fallback heuristic.
- Frontend uses Supabase anonymous auth and sends token in Socket handshake.
- Backend validates token and persists seat/event data to Supabase when server env is configured.
- Lobby and room code are server-driven via Socket events: `create_room`, `join_room_code`, `request_lobby`.
