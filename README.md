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

## Supabase Auth Setup (Google OAuth)

To enable Google sign-in you need a Supabase project with the Google provider configured:

1. **Create a Google OAuth client** in the [Google Cloud Console](https://console.cloud.google.com/apis/credentials):
   - Application type: **Web application**
   - Authorized redirect URI: `https://<YOUR_PROJECT_REF>.supabase.co/auth/v1/callback`

2. **Enable Google provider** in the Supabase dashboard:
   - Go to **Authentication → Providers → Google**
   - Toggle **Enable**
   - Paste your Google **Client ID** and **Client Secret**

3. **Set Site URL** in the Supabase dashboard:
   - Go to **Authentication → URL Configuration**
   - **Site URL**: your production URL (e.g. `https://cardpilot.app`)
   - **Redirect URLs**: add all environments, e.g.:
     - `http://localhost:5173` (local dev)
     - `https://cardpilot.app` (production)
     - Any Netlify preview URLs if needed

4. **Set environment variables** (see `.env.example`):
   - Web: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
   - Server: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`

When Supabase is not configured (env vars unset), the Google button is hidden and the app falls back to guest/local mode.

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
