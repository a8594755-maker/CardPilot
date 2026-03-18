# CardPilot UX Audit & Improvement Plan

---

## 0. Restatement: Goals & Pain Points (5 sentences)

1. **CardPilot is a play-money Texas Hold'em (NLH) 6-max cash table training app** with a real-time GTO coaching sidebar, targeting players who want to improve their preflop/postflop decisions.
2. **The target audience spans from beginners to intermediate players** — beginners need handholding (what is a blind? what does "raise to" mean?), while intermediates want fast-paced, GTO-aligned practice.
3. **Current pain point #1: The new-user flow is too abrupt** — after auth, the user sees a lobby with no guidance on how to create a room, sit down, or start a hand; there is no tutorial or contextual help.
4. **Current pain point #2: The UI has mixed Chinese/English text** (e.g., "你的回合", "處理中…", "發一次/發兩次", "確定要關閉房間嗎"), and many interactive elements are extremely small (11px buttons, w-24 slider), making the experience confusing and error-prone especially on mobile.
5. **Current pain point #3: The game lacks emotional feedback** — no sounds, no animations on deal/action/win, no celebration on winning, no "oof" on a bad beat — the experience feels clinical rather than engaging, which hurts session length and D1 retention.

---

## 1. Experience Issue Checklist (18 items)

### New User Onboarding

| #   | Issue                                                                                                                                                                                                       | Severity | Impact                   |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------ |
| 1   | **No interactive tutorial / first-hand walkthrough.** OnboardingModal is just "You're All Set!" with zero poker education. A beginner has no idea how to create a room, sit, or what the GTO sidebar means. | **P0**   | Retention, Conversion    |
| 2   | **Mixed Chinese/English UI copy.** Action hints ("已跟上，可以 Check"), all-in prompt ("發一次/發兩次"), host controls ("確定要關閉房間嗎"), and status messages are in Chinese while the rest is English.  | **P0**   | Retention, Word-of-mouth |
| 3   | **No poker glossary or tooltip system.** Terms like "SB", "BB", "UTG", "GTO", "EV", "streetCommitted" are shown raw without explanation.                                                                    | **P1**   | Retention                |

### Game Pace / Flow

| #   | Issue                                                                                                                                                   | Severity | Impact                   |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------ |
| 4   | **No quick-play / auto-match.** User must manually create or know a room code. No "Play Now" button that auto-seats into an open table.                 | **P0**   | Session count, Retention |
| 5   | **Winner overlay blocks interaction and auto-dismisses vaguely** ("Next hand in a few seconds..."). No explicit countdown or "Deal Next" button.        | **P1**   | Pace, Sessions/hour      |
| 6   | **No pre-action buttons (auto-fold / auto-check-fold / auto-call).** Players waiting for their turn have nothing to do, slowing down multi-player flow. | **P1**   | Pace                     |

### Controls & Touch Accuracy

| #   | Issue                                                                                                                                            | Severity | Impact                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------ | -------- | -------------------------- |
| 7   | **Action buttons are tiny** (11px text, ~32px tap target). Mobile players will misclick frequently. iOS/Android HIG recommend ≥44px tap targets. | **P0**   | Mistouch rate, Frustration |
| 8   | **Raise slider is only w-24 (96px wide)** — nearly impossible to set a precise amount on mobile. No numeric input alternative.                   | **P0**   | Mistouch, EV leak          |
| 9   | **No confirmation for irreversible high-stakes actions** (All-In). A single accidental tap commits entire stack.                                 | **P1**   | Trust, Frustration         |
| 10  | **No undo/cancel window** after pressing an action button. `actionPendingRef` immediately locks out further input.                               | **P2**   | Mistouch rate              |

### Information Presentation

| #   | Issue                                                                                                                                     | Severity | Impact                       |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------- |
| 11  | **GTO sidebar is hidden on screens < lg** (`hidden lg:flex`). Most mobile users never see the core coaching feature.                      | **P0**   | Feature discovery, Retention |
| 12  | **No pot odds / equity display for beginners.** The app shows raw pot number but doesn't contextualize it (pot odds, SPR).                | **P1**   | Learning, Sessions           |
| 13  | **Hand history "Analyze Now" produces random scores** (`Math.round(50 + Math.random() * 50)`). This erodes trust in the coaching product. | **P1**   | Trust, Word-of-mouth         |

### Matchmaking / Waiting

| #   | Issue                                                                                                       | Severity | Impact                 |
| --- | ----------------------------------------------------------------------------------------------------------- | -------- | ---------------------- |
| 14  | **Lobby refresh is manual** (user must click "Refresh" button). No real-time room list update or auto-poll. | **P1**   | Wait time, Funnel drop |
| 15  | **No "waiting for players" countdown or player-count threshold auto-start.** Host must manually click Deal. | **P2**   | Pace                   |

### Visual & Audio Feedback

| #   | Issue                                                                                                                                | Severity | Impact                     |
| --- | ------------------------------------------------------------------------------------------------------------------------------------ | -------- | -------------------------- |
| 16  | **Zero sound effects.** No deal sound, no chip sound, no win/loss fanfare, no turn notification. Poker without audio feels lifeless. | **P0**   | Engagement, Session length |
| 17  | **Card dealing has no animation.** Cards appear instantly. No flip, no slide, no suspense on community card reveals.                 | **P1**   | Engagement                 |

### Trust & Fairness

| #   | Issue                                                                                                                                                                        | Severity | Impact               |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | -------------------- |
| 18  | **No provably-fair / deck-hash verification exposed to client.** Blueprint mentions `deckSeedHash` but it's not implemented. Players have no way to verify shuffle fairness. | **P2**   | Trust, Word-of-mouth |

---

## 2. Three "Quick Win" Changes (1–3 days each)

### Quick Win A: Full English Localization + Action Button Resize

**What to change:**

- Replace all remaining Chinese strings in `App.tsx` with English equivalents.
- Increase action button tap targets to ≥ 44px height, text to ≥ 14px.
- Widen raise slider to `w-48` minimum, add a numeric input box next to it.

**Why it works:**

- Eliminates the #1 confusion for English-speaking users.
- Reduces mistouch rate immediately (industry standard: 44px minimum touch target).

**Files to modify:**

- `apps/web/src/App.tsx` — ~15 Chinese strings to replace, ActionBar component button classes, slider width.

**Acceptance criteria:**

- [ ] Zero Chinese characters in rendered UI (grep test).
- [ ] All action buttons ≥ 44px height (measured via DevTools).
- [ ] Raise slider ≥ 192px wide on mobile viewports.
- [ ] Numeric raise input accepts typed values, clamps to [min, max].

---

### Quick Win B: Mobile GTO Coach (Bottom Sheet)

**What to change:**

- On screens < lg, show a small floating "GTO" pill at bottom-right.
- Tapping it opens a bottom-sheet overlay with the same advice content (mix bars, recommendation, explanation).
- Auto-open on hero's turn if advice is available.

**Why it works:**

- The GTO coach is the app's differentiator. Hiding it on mobile (the majority viewport) means most users never experience the core value prop.

**Files to modify:**

- `apps/web/src/App.tsx` — new `GtoBottomSheet` component, conditional render replacing `hidden lg:flex`.

**Acceptance criteria:**

- [ ] On viewport < 1024px, GTO pill is visible and tappable.
- [ ] Bottom sheet shows mix bars, recommendation, explanation.
- [ ] Auto-opens when `advice` state updates and hero is actor.
- [ ] Dismissible with swipe-down or tap-outside.

---

### Quick Win C: "Play Now" Quick-Match Button

**What to change:**

- Add a prominent "Play Now" button at the top of the lobby.
- Logic: find the first open public room with available seats → auto-join → auto-sit at first empty seat with default buy-in. If no room exists, auto-create one with default settings.

**Why it works:**

- Removes the biggest friction in the new-user funnel: "I opened the app, now what?"
- Reduces time-to-first-hand from ~45s (create room → configure → sit → wait) to ~5s.

**Files to modify:**

- `apps/web/src/App.tsx` — new button + logic in lobby view.
- `apps/game-server/src/server.ts` — optional: new `quick_match` socket event that returns a suitable room.

**Acceptance criteria:**

- [ ] "Play Now" button visible on lobby, above room list.
- [ ] Clicking it joins an existing open room OR creates a new default room.
- [ ] Auto-sits player at first available seat with mid-range buy-in.
- [ ] Time from click to seeing table < 3 seconds (local server).

---

## 3. Three Medium-Term Changes (1–2 weeks each)

### Medium A: Interactive First-Hand Tutorial

**Implementation direction:**

- Create a `TutorialOverlay` component that uses step-by-step highlights (spotlight + tooltip).
- Steps: (1) "This is the lobby — tap Play Now" → (2) "You're at the table — these are your cards" → (3) "The GTO coach recommends Raise — try it!" → (4) "You won! Here's how the pot was distributed" → (5) "Check your hand history for analysis".
- Store `tutorialCompleted` in localStorage. Show on first login.
- Tutorial uses a scripted/mock hand (local-only, no server) so it works instantly.

**Risks:**

- Tutorial can get out of sync with UI changes. Mitigate by using data-testid anchors.
- Mock hand engine must mirror real engine behavior.

**Event tracking needed:**

- `tutorial_started` — user sees step 1
- `tutorial_step_completed` — { step: number, duration_ms }
- `tutorial_completed` — user finishes all steps
- `tutorial_skipped` — { at_step: number }

---

### Medium B: Sound & Animation System

**Implementation direction:**

- Add a `SoundManager` singleton using Web Audio API / Howler.js.
- Sounds: card_deal, card_flip, chip_bet, chip_win, turn_notification, timer_warning, all_in_drama.
- Animations: card slide-in (CSS transform + opacity), community card flip (3D CSS), chip movement to pot (FLIP technique), winner celebration (confetti/particles).
- Add a mute toggle in the header bar, persist preference.

**Risks:**

- Audio autoplay is blocked on mobile until user interaction. Mitigate by unlocking AudioContext on first tap.
- Large audio files increase bundle. Use compressed .webm, lazy-load.

**Event tracking needed:**

- `sound_muted` / `sound_unmuted`
- `animation_preference` — (if we add a reduced-motion toggle)

---

### Medium C: Pre-Action Queue + All-In Confirmation

**Implementation direction:**

- When it's NOT the player's turn, show grayed-out pre-action checkboxes: "Auto-Fold", "Check/Fold", "Auto-Call Any".
- When the turn arrives, if a pre-action is set and still valid, execute it instantly with a brief flash.
- For All-In: add a 1.5s hold-to-confirm or a two-step tap (tap → "Confirm All-In?" appears → tap again).

**Risks:**

- Pre-actions can become invalid if another player raises. Must validate on turn arrival and clear if invalid.
- Hold-to-confirm might feel slow for experienced players. Offer a "skip confirmation" toggle in profile.

**Event tracking needed:**

- `pre_action_set` — { action, street }
- `pre_action_executed` — { action, was_valid }
- `pre_action_invalidated` — { reason }
- `all_in_confirmed` — { method: "hold" | "double_tap" }
- `all_in_cancelled` — confirmation was shown but user backed out

---

## 4. Tracking & Measurement Plan

### 4.1 New User Funnel

| Step                | Event Name             | Properties                                 |
| ------------------- | ---------------------- | ------------------------------------------ |
| Auth complete       | `auth_completed`       | method: guest/email/google                 |
| Tutorial start      | `tutorial_started`     | —                                          |
| Tutorial complete   | `tutorial_completed`   | duration_ms, steps_completed               |
| Enter lobby         | `lobby_viewed`         | rooms_available: number                    |
| Click Play Now      | `quick_match_clicked`  | —                                          |
| Join room           | `room_joined`          | method: quick_match/code/list, room_age_ms |
| Sit down            | `seat_taken`           | seat_index, buy_in, time_since_join_ms     |
| First hand dealt    | `first_hand_dealt`     | time_since_auth_ms                         |
| First bet placed    | `first_bet_placed`     | action, time_since_deal_ms                 |
| First hand complete | `first_hand_completed` | result: win/lose, duration_ms              |
| Return to lobby     | `lobby_returned`       | hands_played, session_duration_ms          |

**Funnel KPIs:**

- Auth → First hand: target < 60s (currently estimated ~90s+)
- First hand → 5th hand: target > 70% (session stickiness)
- D1 retention: target > 25%

### 4.2 In-Game Core Metrics

| Metric                       | Event / Computation                                        | Notes                       |
| ---------------------------- | ---------------------------------------------------------- | --------------------------- |
| Wait time per hand           | `hand_started` minus previous `hand_ended`                 | Target < 5s with auto-deal  |
| Hand duration                | `hand_ended.timestamp` - `hand_started.timestamp`          | Target 20–45s for 6-max     |
| Actions per hand per player  | Count of `action_submitted` per handId per userId          | Avg ~3–4 expected           |
| Mistouch rate                | Count of `action_cancelled` or undo events / total actions | Target < 2%                 |
| Fold-on-turn rate            | `action_submitted` where action=fold at street arrival     | High = UX issue or boredom  |
| GTO sidebar view rate        | `gto_sidebar_viewed`                                       | Target > 60% of hands       |
| GTO advice follow rate       | Compare `action_submitted.action` vs `advice.recommended`  | Core product metric         |
| Deviation score distribution | Histogram of `advice_deviation.deviation` values           | Track improvement over time |
| Abandon timing               | `session_ended` with last_street context                   | Identify when users quit    |
| Pre-action usage rate        | `pre_action_set` / total turns                             | Measures pace satisfaction  |

### 4.3 Performance & Reliability

| Metric                        | Source                                                          |
| ----------------------------- | --------------------------------------------------------------- |
| Socket connect time           | Client-side: `connect` event timestamp - `io()` call timestamp  |
| Reconnect count per session   | Count `disconnect` → `connect` pairs                            |
| Snapshot latency              | Server-side: time from `action_submit` to `table_snapshot` emit |
| Client render FPS during hand | `requestAnimationFrame` sampling (dev builds)                   |

---

## 5. Test Cases (20 cases, Given-When-Then)

### Disconnect & Reconnect

**TC-01: Reconnect mid-hand restores state**

- Given: Player A is in a hand with hole cards [Ah, Kd], it's their turn, pot = 500
- When: Player A's network disconnects and reconnects within 30 seconds
- Then: Player A sees the same hand state (hole cards, pot, board, legal actions), and can continue acting

**TC-02: Disconnect timeout triggers auto-fold**

- Given: Player A is the current actor, action timer = 15s, time bank = 0s
- When: Player A disconnects and does NOT reconnect within 15 seconds
- Then: Server auto-folds Player A, next player becomes actor, `action_applied` event is broadcast with action=fold

**TC-03: Reconnect after hand ended**

- Given: Player A was in hand #H1, disconnects. While disconnected, hand #H1 ends and hand #H2 starts
- When: Player A reconnects
- Then: Player A receives `table_snapshot` with current hand #H2 state, their previous seat is preserved, they are dealt into #H2 if still seated

### Timer & Timeout

**TC-04: Action timer countdown reaches zero**

- Given: Player B is current actor with 10s remaining, no time bank
- When: 10 seconds elapse without any action
- Then: Server auto-folds Player B, emits `action_applied` with fold, and `player_timed_out` log entry is created

**TC-05: Time bank activation**

- Given: Player C has 5s action timer remaining and 30s time bank
- When: Action timer reaches 0
- Then: Time bank starts counting down from 30s, UI shows amber timer indicator, player can still act

**TC-06: Consecutive timeout auto-sit-out**

- Given: maxConsecutiveTimeouts = 3, Player D has timed out 2 consecutive times
- When: Player D times out a 3rd time
- Then: Player D is automatically stood up from the table, `PLAYER_SAT_OUT` log entry is created

### Auto-Fold & Minimum Raise

**TC-07: Auto-fold when facing bet with 0 chips**

- Given: Player E has stack = 0 after posting BB (all-in on blind)
- When: Another player raises
- Then: Player E is not prompted for action (already all-in), hand continues correctly

**TC-08: Minimum raise validation**

- Given: BB = 2, current bet = 6 (a raise to 6), minRaiseTo = 10
- When: Player F tries to raise to 8
- Then: Server rejects with error "raise must be at least 10", player's state is unchanged

**TC-09: Raise exactly equal to current bet is rejected**

- Given: Current bet = 10
- When: Player tries `action: "raise", amount: 10`
- Then: Server throws "raise must increase current bet"

### All-In Scenarios

**TC-10: All-in with less than minimum raise**

- Given: Player G has stack = 5, minRaiseTo = 10, currentBet = 6
- When: Player G goes all-in (commits remaining 5 chips)
- Then: All-in is accepted (all_in is always legal if player has chips), `streetCommitted` = previous + 5, `allIn = true`

**TC-11: All-in triggers run-it-twice prompt**

- Given: Two players remaining, both go all-in, runItTwiceMode = "ask_players"
- When: Last all-in action is applied
- Then: `allInPrompt` is emitted to the underdog player with winRate, recommendedRunCount, and allowedRunCounts

**TC-12: Run-it-twice produces correct split pot**

- Given: Pot = 1000, both players all-in, underdog chooses runCount = 2
- When: Server performs two runouts
- Then: First board awards floor(1000/2) = 500 to its winner, second board awards 500 to its winner. If same player wins both, they get 1000. Stacks are updated correctly.

### Edge Cases: Chips & Pot

**TC-13: Blind posting with insufficient stack**

- Given: Player H has stack = 1, smallBlind = 5
- When: Hand starts and Player H is in SB position
- Then: Player H posts 1 (all their chips), `allIn = true`, `streetCommitted = 1`, pot includes 1 from SB

**TC-14: Split pot on tie (identical hands)**

- Given: Player I has [Ah, Kh], Player J has [As, Ks], board = [2c, 5d, 8h, Tc, Qd], pot = 200
- When: Showdown occurs
- Then: Each player receives 100, `winners` array has 2 entries each with amount = 100

**TC-15: Odd chip in split pot**

- Given: 3-way tie, pot = 100
- When: Showdown distributes pot
- Then: Two players get 34, one gets 33 (or similar floor + remainder distribution). Total distributed = 100 exactly.

### Concurrent Operations

**TC-16: Two players submit action simultaneously**

- Given: It's Player K's turn (actorSeat = K)
- When: Player L (not the actor) submits an action at the same time
- Then: Player L receives error "not your turn", Player K's action is processed normally

**TC-17: Player sits while hand is in progress**

- Given: Hand is active with 3 players
- When: Player M clicks an empty seat and confirms buy-in
- Then: Player M is added to `players` array with `inHand = false`, they will be dealt into the NEXT hand

**TC-18: Player stands up during active hand**

- Given: Player N is in the current hand, has not yet acted this street
- When: Player N clicks "Stand Up"
- Then: Player N is folded from the current hand, removed from seat. Hand continues with remaining players.

### Host Controls

**TC-19: Pause during active hand**

- Given: Hand is in progress, it's Player O's turn
- When: Host clicks Pause
- Then: Action timer stops, Player O cannot submit actions, `room.status = "PAUSED"`, `GAME_PAUSED` log is created. On resume, timer resumes from where it stopped.

**TC-20: Close room with players seated**

- Given: Room has 4 players seated, hand is NOT active
- When: Host confirms room closure
- Then: All players receive `room:left` event, redirected to lobby. Room is removed from lobby list. If hand WAS active, it should be aborted first (`abortHand` returns bets).

---

## 6. Priority Implementation Roadmap

```
Week 1 (Quick Wins):
  Day 1-2: Quick Win A — English localization + button resize
  Day 2-3: Quick Win B — Mobile GTO bottom sheet
  Day 3:   Quick Win C — Play Now quick-match

Week 2-3 (Medium):
  Medium A: Interactive tutorial (1 week)
  Medium C: Pre-action queue + All-In confirm (parallel, 3 days)

Week 3-4 (Medium):
  Medium B: Sound & animation system (1 week)

Week 5+:
  Provably-fair deck verification
  Advanced postflop GTO coaching
  Social features (chat, friends, invite)
  Performance optimization (lazy-load, code splitting)
```

---

## Appendix: Chinese Strings to Replace

| Location (approx line) | Current Chinese                            | Suggested English                                              |
| ---------------------- | ------------------------------------------ | -------------------------------------------------------------- |
| App.tsx:1003           | `▶ 你的回合`                               | `▶ Your Turn`                                                  |
| App.tsx:800            | `確定要關閉房間嗎？所有玩家將被送回大廳。` | `Close this room? All players will be sent back to the lobby.` |
| App.tsx:1198           | `All-In 發牌選擇`                          | `All-In Run-Out Option`                                        |
| App.tsx:1199           | `你的勝率:`                                | `Your Win Rate:`                                               |
| App.tsx:1212           | `發一次`                                   | `Run It Once`                                                  |
| App.tsx:1219           | `發兩次`                                   | `Run It Twice`                                                 |
| App.tsx:2346           | `已跟上，可以 Check`                       | `Matched — you can Check`                                      |
| App.tsx:2347           | `需跟注 ${callAmt}`                        | `To call: ${callAmt}`                                          |
| App.tsx:2356           | `處理中…`                                  | `Processing...`                                                |
| App.tsx:753            | `Need ≥2 players`                          | (already English, OK)                                          |
