# Continuation after the capped-history audit failure

The original guarded owner, trainer, launcher and audit child are OS-confirmed
terminal. Its unchanged status records a fail-closed stop on dynamic_pool_healthy.
No endpoint evaluation had begun. The original failed audit is immutable at SHA256
11486bcb5582a574b875baf21cf7e672f742bcd5b64426a6aefbe098d00a44f2.

The new archive-window proof reconstructs every new candidate and exact pool
selection/assignment across all three seeds (664 candidates, 27 checkpoint windows,
1,328 suffix assignments). Its SHA256 is
3409300bf825a45aae9559c580a83ce67e732cce64425c2fa41dc326f0770586.
The terminal windows intentionally retain only 200 candidates; the original audit
incorrectly required all 220-223 new candidates to fit inside each final window.
Twelve synthetic corruption/coverage tests pass. Independently, all three frozen
endpoints and the Seed2 recovery segments passed the existing post-hoc mechanics
and inherited observation-bridge verification. This does not repair Seed2's deal
freshness or authorize a clean three-seed scaling claim.

The proof also confirms actual frozen loss-K-best scoring used
policy_loss + 0.5*log1p(value_loss), while a historical metadata formula string
said coefficient 1. The original strings are retained, not silently rewritten.
This descriptive mismatch is not a change to the executed optimizer or selector.

Run only `python research/experiments/v6-static-current-kl-4m-scale-20260904/run_pool_qualified_evaluation.py`.
Its --preflight-only mode starts no workers and creates no evidence. The execution
creates a new ownership/status directory, guarded_followthrough_v2_pool_qualified,
without rewriting v1. The new live owner is the sole writer of this experiment
record; inspect its PID/create_time and active child before any takeover.

All original endpoints, four anchors, evaluation seeds, 2,048 pairs per anchor,
both seats, 20k-state drift budgets/seeds, original aggregate and deviation report
remain unchanged. It never restarts training, replaces an endpoint, reuses an
existing evaluation destination, or runs a fourth seed. It checks the precise
observed original failures and both separately qualified proofs before new hands.
Any other failure stops. Original failed gates remain false in the original report.

Production source stays unchanged until this continuation and all children are
terminal. The existing GPU qualification entry point still recognizes only the v1
handoff; after this continuation completes, add a separately tested, explicit v2
handoff adapter rather than rewriting v1 status or bypassing the live-process check.
This scheduling adaptation must preserve the already fixed GPU diagnostic recipe,
parent, ABBA order, budget, integrity requirements and cost decision.

At EVIDENCE_READY_FOR_RESEARCH_ANALYSIS, the main researcher reads both reports
and the pool proof, finishes the same experiment with full accounting/hashes, then
chooses the next allocation. No automatic 8M promotion or new method is authorized.
