# Fixed-deal recovery integrity: observed finding and bounded implementation

This is an infrastructure audit, not a new policy-training experiment. The live
4M trainer, weights, optimizer, replay, session and hand evidence were not edited
or restarted. The user-authorized efficiency-first policy is now documented in
research/RESEARCH_POLICY.md and referenced from AGENTS.md.

## Reproduced evidence

The original Seed2 process and both recoveries reuse worker seed base
2026300200 and deal start 38300000. Each single-env worker initializes its deal
cursor directly from that start on process creation. The frozen original guard
and recovery1 checkpoints plus the saved recovery2 metric prefix reconstruct:

- 1,961,132 evidenced physical executions in this 4M-stage Seed2 suffix;
- 1,519,687 unique deterministic (worker seed, env, deal index) identities;
- 441,445 repeated deal exposures, counted as sum of interval lengths minus
  union length, including multiplicities across the three attempts.

These are prefix results, not final 4M counts. Unknown uncheckpointed work is
excluded. Repeated deal identities do not imply identical actions or trajectories.
Actual terminal execution counts are NOT reduced; the defect concerns freshness,
coverage, exact-resume claims, and interpretation as an independent scale control.
Uninterrupted source/optimizer/assignment preservation is a separate question.

Report SHA256: 3c96eac76b92bacd479068573df76e7d27fe7e913ff65254c275c77f6cd026a3.
The report stores the observed metric, prefix byte length and SHA, checkpoint
SHA values and per-worker intervals. Its replay command is:

    python scripts/alpha_holdem/fixed_deal_resume_integrity.py --verify-report research/experiments/v6-resume-deal-stream-integrity-20260904/observed_overlap.json

## Implemented in isolation

The standalone module reconstructs overlap and rejects a proposed resume that
reuses/touches known intervals. It examines all supplied attempts, not merely the
most recent short recovery. It fails closed on missing counters, unsupported
multi-env/mirrored interpretations, or an unresolved crash suffix. A positive
result is explicitly statistical continuation, never bitwise uninterrupted resume.

13 focused tests passed, including 200 randomized interval-union comparisons
against explicit identity sets. Four logger tests also passed. The initial test
collection failed because of a package import path; that test-only import was
corrected before any diagnostic run. Frozen report replay passed exactly.

## Pending safe-boundary integration (not claimed complete)

The module is NOT yet wired into train_v5.py because that source is used by the
active sequential Seed2/Seed3 launcher. Do not modify it mid-run. At the safe
boundary, extend the runner/trainer startup contract to require an auditable
attempt ledger and reject reused windows BEFORE starting workers. Do not rely
on optimizer/replay restoration or a large global cumulative count as proof.

Unknown crash suffixes require a durable pre-reserved namespace/window or
explicit per-worker cursor evidence; a gap based only on the last checkpoint
is not automatically sufficient. Preserve training RNG separately and label
legacy migrations as statistical continuation. Exercise interrupted real-worker
resume before declaring integration complete.

Recompute the final overlap at the frozen Seed2 endpoint. Analyze this seed as
deviated exposure, not an independent clean replication. Do not silently discard
it, subtract executed hands, retrain its entire prefix, or use the original 4M
promotion gate without adjudicating the deviation. Seed1 and Seed3 have not been
found affected by this particular same-stage recovery defect; that is not a claim
that all other historical boundaries have been exhaustively audited.
