# Fixed Seed1 4M external development calibration

This protocol is written after the 4M internal results were inspected and before any new external hands. It is not a final benchmark, not a best-seed selection, and not a retrospective claim of preregistration. Do not launch until the existing managed-resume GPU qualification is terminal and its experiment is finished.

## Decision value and inputs

The static-current-KL family's internal 2M-to-4M slope is uncertain: pooled +1.2625 bb/100, with fixed incident-unaffected Seed1/3 +0.0460. There has not yet been a corresponding external measurement of these checkpoints. Measure external transfer before committing to another large allocation. Do not reject long-horizon learning solely because this development score is negative.

Use the original incident-unaffected Seed1 checkpoint at iteration882 / 4,197,976 physical executions:
`research/experiments/v6-static-current-kl-4m-scale-20260904/seed1/latest.pt`
SHA256 `7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f`.
Seed1 is fixed by identity, not the best of the observed three (Seed2 had the largest internal point estimate). Do not substitute the GPU diagnostic descendants. No training, temperature fitting, action rules, or Slumbot action-label fitting occurs here.

Freeze the runtime snapshot, source helper hashes, model copy, 200bb physical-v6 rules, legacy-v4 observation bridge, legality mapping and generic greedy execution before requests. All streets use the learned policy; no search or Slumbot-specific exceptions. CPU inference, policy temperature0, selected slot must equal masked argmax and behavior probability1.

## Fixed sampling and stopping

Exactly eight new sessions, 2,500 hands each, total20,000. Session IDs:
`v6_static_seed1_4m_greedy_fresh20k_20260904_s01` through `s08`.
Policy seeds2026330101 through2026330108 (client seeds do not control Slumbot's server deals).
No admission5k, optional extension, session replacement, outcome-dependent stopping or pooling with older cohorts. Existing output refusal is mandatory. A transport/process/evidence failure preserves the original partial cohort and cannot be silently repaired by rerunning hands. All sessions already launched may finish naturally. A failed cohort is not a completed measurement.

## Evidence and statistics

Retain per-hand raw JSONL, decisions, terminal checks, request journal, token chains, session seeds, exact argv, runtime/model hashes, timestamps and exit codes. Keep running accounting synchronized to complete durable raw records. After all sessions finish, replay every decision and terminal result; require all eight model/runtime contracts and disjoint token chains, including comparison with prior completed audits. Run the separate session-independence audit.

Primary descriptive quantity: raw mean bb/100 and normal95% hand-level interval. Also report equal-session means, the session-level t7 interval, both seats and positive-session count. The raw interval assumes independent hand noise; the eight-session interval is a limited sensitivity check, not proof of arbitrary temporal independence or a guaranteed formal benchmark interval. No significance-based early stopping.

Compare descriptively to the already completed same-execution-contract Standard10 fresh20k cohort at -24.5683 bb/100, with an unpaired difference interval incorporating uncertainty in both cohorts. The older historical Standard10 greedy -11.4275 is a separately labeled reference, not the matched-contract baseline. Earlier integrated-recipe 1M/2M scores are different policies, not this family's learning curve. Cohort differences and time effects remain possible; no causal attribution from a losing hand.

This experiment always requires research review and never automatically authorizes100k, promotes a checkpoint or marks the goal complete. A positive development result would justify designing a separate fully frozen blind test with its own fixed sample size/stopping rule. A negative result is classified jointly with its uncertainty, internal curve, source preservation and measured cost; it does not automatically terminate the entire algorithm family. If transfer remains indistinguishable from the source, prefer one substantive learning control over many short proxy-only tweaks.

## Reuse and launch

Reuse the existing journaled external runner and its legacy-bridge adapter without modifying their historical files. Freeze helper hashes and capture them in this experiment's code provenance. A local wrapper changes only this experiment's identity, fixed source, statistics and development-only decision label; evidence validation and session execution remain intact.

Exact launch: `python research/experiments/v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904/run_pilot.py`.
