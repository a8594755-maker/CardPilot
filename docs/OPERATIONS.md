# Operations Guide

## Runtime Configuration

Server runtime settings are centralized in `apps/game-server/src/config.ts` and validated at startup.

Key runtime values:

- Table timing: `HAND_IDLE_TIMEOUT_SECONDS`, `SHOWDOWN_DECISION_TIMEOUT_SECONDS`, `RUN_COUNT_DECISION_TIMEOUT_SECONDS`
- Room lifecycle: `ROOM_EMPTY_TTL_MINUTES`
- Network: `PORT`, `CORS_ORIGIN`
- Room defaults and bounds: max seats, blinds, buy-in multipliers, room-code format

Config rules:

- Missing numeric env values fall back to safe defaults.
- Invalid numeric env values fail fast with a clear startup error.
- Supabase variables are validated as a set:
  - Set all of `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, or leave all unset.
  - If only a subset is configured, the server disables Supabase and runs in guest/local mode with a warning.
  - Set `SUPABASE_STRICT_ENV=true` to fail fast instead.

## Environment Variables

Use `.env.example` (repo root) and `apps/game-server/.env.example` as the source of truth.

Production-critical variables:

- `PORT`
- `CORS_ORIGIN`
- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_STRICT_ENV` (optional; set to `true` for fail-fast partial-config validation)

Web variables:

- `VITE_SERVER_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`
- `VITE_CONTACT_EMAIL`

## Health Endpoints

- `GET /health`: legacy basic health response
- `GET /healthz`: operational health response with uptime, commit, room/table counts, and Supabase mode
- `GET /version`: build commit metadata

Example:

```bash
curl -s http://127.0.0.1:4000/healthz | jq
```

## Startup

From repo root:

```bash
npm install
npm run dev
```

Server only:

```bash
npm run dev -w @cardpilot/game-server
```

## Graceful Shutdown

The game server handles `SIGINT` and `SIGTERM` by:

1. Stopping new activity (timers/prompts/autodeal cleanup).
2. Closing open room sessions.
3. Closing Socket.IO and HTTP listeners.
4. Exiting cleanly.

If cleanup exceeds 12 seconds, shutdown is forced with a non-zero exit code.

## Logging

Structured logs are emitted as JSON via `apps/game-server/src/logger.ts`.

Example fields:

- `ts`
- `level`
- `event`
- `tableId`
- `handId`
- `seat`
- `userId`

This format is suitable for log aggregation and incident triage.
