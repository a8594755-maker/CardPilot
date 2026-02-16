# CardPilot In-Game UX Spec — PokerNow-Style Flow

## Core Rule
**Only use a blocking modal when the user must explicitly confirm a risky action or make a required choice.**

### When to use each feedback pattern

| Pattern | Use case | Examples |
|---------|----------|---------|
| **Blocking modal** | Risky/irreversible action requiring explicit confirmation | Unnecessary fold (check is free), Leave seat, Exit room |
| **Toast** | Transient status info, action confirmations, errors | "You: Call 200", "Connected", "Error: …" |
| **Seat highlight + delta tag** | Winner feedback at hand end | Gold glow on winner seat, "+4 BB" / "−2 BB" tags |
| **Side drawer** | Detailed info the user can optionally inspect | Hand Summary, Room Log |
| **Inline banner** | Contextual info within the table area | Showdown decision (Show/Muck), All-in prompt |

---

## A) Bottom Action Bar

- Sticky bottom, 44px+ touch targets
- **FOLD** (muted/danger) — always visible when it's your turn
- **CHECK** (green) — shown when `canCheck`
- **CALL** (blue) — shows call amount: `CALL 0.7 BB`
- **RAISE** (red) — label only, **no amount shown**. Opens RaiseSheet on click.
- **ALL-IN** — small secondary button, requires confirm tap

### Pre-action (not your turn)
- "Check/Fold", "Check", "Fold" toggle buttons
- Active pre-action shown as small badge, easy to clear with ✕

---

## B) Raise Sheet

- Opens as bottom tray (transform slide-up, 150–200ms)
- **"Your Raise"** — big number (chips) + BB equivalent
- **Presets**: Min, ½ Pot, ¾ Pot, Pot, All-in (context-dependent)
- **Slider** + **+/−** step buttons + numeric input
- **Actions**: Back (ghost) / Confirm Raise (red, 2× width)
- No backdrop-filter blur on the sheet itself

---

## C) Hand End / Result UX

### Normal hands (no all-in showdown)
1. **No blocking modal.** Settlement data is captured but NOT shown as overlay.
2. Winner feedback:
   - Seat glow (gold ring) on winner(s) for ~1.5s
   - Stack delta tag near seat: "+4 BB" (green) / "−2 BB" (red)
   - Toast: "Winner: PlayerName +400"
3. **Timing**: Auto-advance after **1.5s** (configurable 1.2–2.0s)
4. **Skip**: Click anywhere on table, or press Space/Enter to advance immediately

### All-in hands (showdown with runout)
1. **Still no blocking modal by default.**
2. Winner feedback same as above but lingers **4s** (configurable 3–5s)
3. Board + revealed hands shown directly on table (already works via revealedHoles)
4. Subtle hand-name badges on revealed seats ("PAIR", "STRAIGHT")
5. **Skip**: Same interactions — click/Space/Enter

### Hand Summary access
- Small "📋 Hand Summary" button appears in toast or as a floating pill during the linger period
- Clicking opens a **side drawer** (not modal) with full settlement details
- Also accessible from Room Log / History

---

## D) Showdown / Reveal

- Board and revealed hands shown directly on table (existing behavior)
- Small badges on seats with hand names — subtle, not centered dialogs
- Winner glow distinguishes winner from other revealed hands

---

## E) Confirmation Modals (allowed cases only)

### 1. Unnecessary Fold
- Trigger: User clicks FOLD when CHECK is available
- Copy: "You can check for free. Fold anyway?"
- Buttons: "Check instead" (primary) / "Fold anyway" (ghost)
- Checkbox: "Don't show again this session"
- **Already implemented** in FoldConfirmModal.tsx ✓

### 2. Leave Seat / Exit Room
- Trigger: User clicks leave/exit
- Copy: Clear consequence text
- Buttons: Confirm / Cancel

---

## F) Performance Constraints

- **No `backdrop-filter: blur()` on full-screen overlays** during animations
- RaiseSheet and drawers use `will-change: transform` + `contain: paint`
- Seat highlights use `box-shadow` (GPU composited), not filter
- Toast uses `transform: translateY()` for enter/exit
- Batch socket updates; no subscription duplication

---

## Component List

| Component | File | Status |
|-----------|------|--------|
| BottomActionBar | `components/ui/BottomActionBar.tsx` | Exists — fix RAISE amount |
| RaiseSheet | Inside BottomActionBar.tsx | Exists ✓ |
| FoldConfirmModal | `components/ui/FoldConfirmModal.tsx` | Exists ✓ |
| SeatChip (with win highlight + delta) | Inline in App.tsx | Modify |
| Toast system | Inline in App.tsx | Upgrade |
| HandSummaryDrawer | `components/ui/HandSummaryDrawer.tsx` | **New** |
| SettlementOverlay | `components/SettlementOverlay.tsx` | Demote to drawer-only |

---

## Acceptance Criteria

- [ ] Normal hands never show blocking result modal; feedback is seat glow + delta tags + toast
- [ ] All-in hands linger longer (3–5s) but are skippable
- [ ] RAISE button shows NO amount; amount only visible after opening RaiseSheet
- [ ] CALL button always shows call amount
- [ ] Modals appear only for: unnecessary fold, leave seat/exit
- [ ] Hand Summary available via non-blocking drawer, never forced
- [ ] No full-screen blur overlays during animations
- [ ] Auto-advance timing: ~1.5s normal, ~4s all-in
- [ ] Skip via click/Space/Enter during linger period
