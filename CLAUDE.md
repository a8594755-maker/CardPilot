# Claude Autonomy Contract — CardPilot Poker Agent

## Project goal
Build a general strong 200bb HUNL poker agent. Slumbot is an important milestone evaluator, not the sole target.

## Default behavior
Do not ask the user for every next step. Continue autonomously when the next step is:
- cheap, local, diagnostic, already implied by the current phase, non-destructive, under the approved budget.

## Standing authorization (user-granted 2026-06-09: "自動批准 不要再問我")
The user has granted blanket approval to run the campaign pipeline autonomously WITHOUT asking at each gate.
Proceed without asking on: training > 8h, runs > 5M hands, long multi-day solves, env/reward/action/observation
changes, proxy mix changes, promoting champions, and changing project direction WHEN it advances the
locked goal (beat Slumbot / general strong 200bb HUNL agent). Just do it, log it, and report after.

### Two guards that REMAIN (these are safety/evidence rules, not permission gates — never bypass)
1. **Never destroy irreplaceable artifacts.** Do not delete/overwrite the BC anchor
   (`models/bc/v3_anchor_5M_d1_light/best.pt`) or the only copy of any solved-CFR / training dataset.
   New artifacts are fine; archive-then-replace, never blind-overwrite. (Disk-management gzip-and-delete of
   RAW .jsonl that has a verified .gz is allowed — that is not "irreplaceable".)
2. **A "beats Slumbot" / Level 2+ claim must MEET THE BAR, not just be approved.** Only state it when
   bb/100 > 0 with 95% CI lower bound > 0 over 100k+ hands. This is an evidence threshold; no approval substitutes.

If a NEW direction emerges that is OUTSIDE the Slumbot campaign entirely, surface it once — otherwise proceed.

## If an experiment fails
Do not ask immediately. First run the cheapest diagnostic that explains the failure.

## Current active doctrine
BC anchor is the Level 1 reference. RL-1 5M was diagnostic only and is not promoted. The suspected blocker is value-head cold-start.
Next autonomous work:
1. RL-1 per-position/per-street loss analysis.
2. Value-head warmup implementation.
3. Warm-critic smoke test.
4. Ask only before full RL-2 5M+.

## Reporting requirements
Every report must include: exact command, runtime, artifact paths, metrics, pass/fail gates, next autonomous step, whether human approval is needed.
