# Club System V1 — QA Checklist

## Automated Tests

Run: `cd apps/game-server && npm test`

| #   | Test                                                               | Status |
| --- | ------------------------------------------------------------------ | ------ |
| 1   | Creating a club generates unique code & creates OWNER membership   | ✅     |
| 2   | Joining by code creates MEMBER row idempotently                    | ✅     |
| 3   | Non-member cannot list club tables (via getClubDetail)             | ✅     |
| 4   | Non-admin/non-host cannot create club table                        | ✅     |
| 5   | Club tables identifiable via getClubForTable after room code set   | ✅     |
| 6   | Club tables excluded from public lobby (visibility=private filter) | ✅     |

## Manual QA Steps

### 1. Club Creation

- [ ] User A sends `club_create { name: "Test Club" }`
- [ ] Server responds with `club_created` containing a 6-char code
- [ ] User A appears as OWNER in `club_list_my_clubs` response

### 2. Club Join

- [ ] User B sends `club_join_request { clubCode: "<code>" }`
- [ ] If `requireApprovalToJoin=false`: User B auto-joins, sees club in `club_list`
- [ ] If `requireApprovalToJoin=true`: User B is pending; admin approves via `club_join_approve`
- [ ] Public lobby remains unchanged for User B (no club tables visible)

### 3. Club Table Creation

- [ ] Admin/Host sends `club_table_create { clubId, name: "NL100" }`
- [ ] Server creates a private room (visibility=private, isPublic=false)
- [ ] `club_table_created` response includes roomCode
- [ ] Table does NOT appear in public `lobby_snapshot` for any user

### 4. Non-Member Isolation

- [ ] User C (not in club) sends `join_room_code { roomCode: "<club_table_code>" }`
- [ ] Server responds with `error_event`: "This is a club table. Only active club members can join."
- [ ] User C sends `sit_down` for the club table → blocked with membership error
- [ ] User C sends `seat_request` for the club table → blocked with membership error

### 5. Member Access

- [ ] User B (club member) sends `join_room_code { roomCode: "<club_table_code>" }` → succeeds
- [ ] User B can sit down and play at the club table
- [ ] User B sees club tables via `club_table_list { clubId }`

### 6. Lobby Isolation

- [ ] Refresh public lobby for all users → no club tables appear
- [ ] Club tables only visible through `club_get_detail` / `club_table_list` for members

## Architecture Notes

- **V1 is play-money only**: `club_members.balance` exists but no payment/cashout flows
- **Server authoritative**: All club operations validated server-side via `ClubManager`
- **Club tables**: Created with `visibility: "private"`, filtered from lobby by `emitLobbySnapshot`
- **Access control**: Enforced at `join_room_code`, `join_table`, `sit_down`, `seat_request`

## How to Run Migrations

```bash
# Apply all migrations in order against your Supabase/Postgres instance:
psql $DATABASE_URL -f backend/sql/001_init.sql
psql $DATABASE_URL -f backend/sql/002_supabase_multiplayer.sql
psql $DATABASE_URL -f backend/sql/003_lobby_room_code.sql
psql $DATABASE_URL -f backend/sql/004_hand_history_room_sessions.sql
psql $DATABASE_URL -f backend/sql/005_clubs.sql
```

## How to Verify

```bash
# Run club manager tests
cd apps/game-server && npm test

# Start dev server
npm run dev

# Connect via Socket.IO client and exercise the club_* events
```
