# Clubs Feature — Manual QA Checklist

> **Important:** CardPilot is a **play-money training tool** — not real-money gambling.
> All club credits are virtual.

---

## A. Club Creation & Settings

- [ ] Create a club with name, description, badge color
- [ ] Club code is generated (6 chars, uppercase)
- [ ] Creator is auto-assigned `owner` role with `active` status
- [ ] Club appears in "My Clubs" list after creation
- [ ] Update club name/description/visibility (owner/admin only)
- [ ] Non-admin cannot update club settings

## B. Join & Approval Flows

- [ ] Join club via club code (requireApprovalToJoin=false) → instant join
- [ ] Join club via club code (requireApprovalToJoin=true) → status=pending
- [ ] Pending member cannot see club detail or sit at tables
- [ ] Admin/mod sees pending join requests banner
- [ ] Approve join request → member becomes active
- [ ] Reject join request → member removed
- [ ] Join via invite code bypasses approval requirement
- [ ] Already-member gets "Already a member" error
- [ ] Banned user gets "You are banned" error on join attempt
- [ ] Expired invite code is rejected

## C. Membership & Permissions

- [ ] Owner can promote member → admin
- [ ] Admin can promote member → mod/host (but NOT admin)
- [ ] Mod cannot change roles
- [ ] Member cannot change roles
- [ ] Mod can kick member (lower rank)
- [ ] Mod cannot kick admin (higher rank)
- [ ] Nobody can kick owner
- [ ] Ban/unban flow works (admin/mod → member)
- [ ] Kicked member removed from club list
- [ ] Banned member cannot rejoin

## D. Invites

- [ ] Admin/mod/owner can create invite codes
- [ ] Member cannot create invite codes
- [ ] Invite code has correct max_uses and expiry
- [ ] Revoke invite works
- [ ] Copy invite code to clipboard works in UI

## E. Rulesets

- [ ] Admin can create ruleset with custom rules
- [ ] Set ruleset as default
- [ ] `preventDealMidHand` is always enforced as `true`
- [ ] `canPauseMidHand` is always enforced as `false`
- [ ] `maxSeats` is clamped to 2–9

## F. Club Tables

- [ ] Host/admin/owner can create a club table
- [ ] Member cannot create a club table
- [ ] Club table appears in club detail "Tables" tab
- [ ] Club table uses club rules (stakes, buy-in, timer, etc.)
- [ ] Club table is private (not visible in public lobby)
- [ ] "Join Table" button navigates to table view
- [ ] **Non-member cannot sit at club table** (server rejects sit_down)
- [ ] **Pending member cannot sit at club table**
- [ ] **Banned member cannot sit at club table**
- [ ] Close table works
- [ ] Pause table works (deferred until hand end)

## G. In-Table Experience

- [ ] Club table header shows club name + rules summary
- [ ] Buy-in enforced per club rules (min/max)
- [ ] Action timer uses club rules setting
- [ ] Run-it-twice follows club rules
- [ ] Spectator access follows `allowSpectators` rule
- [ ] Auto-deal follows club dealing rules

## H. UI / UX

- [ ] "Clubs" nav tab appears between "Lobby" and "Table"
- [ ] Play-money disclaimer visible on clubs pages
- [ ] Club badge color renders correctly
- [ ] Club code displayed and copyable
- [ ] Members list shows roles and join dates
- [ ] Audit log shows admin actions (visible to mod+)
- [ ] Responsive on mobile (tabs scroll horizontally)
- [ ] Toast messages for all club actions (create, join, error)
- [ ] "Back" from club detail returns to club list

## I. Security / Server Authority

- [ ] All permission checks happen server-side (not just client)
- [ ] Client cannot forge club membership
- [ ] RLS policies restrict reads to members only
- [ ] Audit log writable only by service role
- [ ] Club tables writable only by service role

## J. Non-Regression

- [ ] Public lobby still works (create room, join room, play hand)
- [ ] Existing table flows unaffected (sit, deal, action, settlement)
- [ ] History page still works
- [ ] Profile page still works
- [ ] No TypeScript build errors
- [ ] All existing tests pass (86+ game-engine tests)
- [ ] All club-manager tests pass (30 tests)
