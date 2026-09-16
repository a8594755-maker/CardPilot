# Managed trainer staging validation (not a production cutover)

Production Seed3 remains active. Do not replace train_v5.py until the complete
sequential 4M launcher is terminal and no worker still imports its source.
The production source remains SHA256
594f1de70f9a6abdf8076fe129a18056b5a3bd84087ad4f6cc2f1498850a6956.
Both production_before_integration.py and staged_candidate.py are preserved.

## Evidence completed

- Three real CPU start/save/resume cycles: 200 + 200 + 200 new terminal hands.
  The third cycle used two environments per worker. All initial model,
  optimizer, replay contents/RNG, available main RNG, counters and iterations
  were preserved. Optimizer steps and replay draws subsequently advanced.
- An isolated real optimizer step followed by injected KeyboardInterrupt:
  100 additional completed environment hands, zero retained complete updates.
  The prior complete checkpoint remained byte-identical; the terminal manifest
  retained the additional execution accounting. These 100 hands are diagnostic
  executions, not added to the committed checkpoint's hand counter.
- Reused namespace and managed-to-legacy mode were rejected before worker
  start. The final candidate additionally rejects any unmanaged fixed-deal
  resume, optimizer reset, or hand-counter reset at argument validation.
- 54 targeted tests pass (assignment origin, atomic checkpoint, durable attempt,
  overlap reconstruction, existing replay and dynamic-pool regressions).
- Existing successful cycles were independently verified with --verify-only:
  no new hands, no checkpoint or completed evidence rewrite.

Total new diagnostic physical environment executions: 700. Hands in retained
complete diagnostic updates: 600. Interrupted/discarded update exposures: 100.
New Slumbot or internal strength-evaluation hands: zero.

## Failures and corrections preserved

Two initial argument rejections generated no hands. The first completed cycle's
replay comparison falsely failed on an intentional NaN sentinel; exact bytewise
array/NaN comparison corrected the verifier, with no retraining.

The next start allocated a namespace and saved its initial checkpoint but failed
before worker launch: legacy assignment replay assumed iteration 1 whereas this
diagnostic fork inherited iteration 882. An explicit SHA-bound initial RNG-origin
checkpoint permits replay from iteration 883 while preserving all contiguous
iteration, record hash, link, assignment and pending-state checks. Failed attempt2
and its consumed namespace remain untouched. Its retry used a new directory and
namespace. Successful future checkpoints serialize their replay origin.

Each resumed child verifies the parent's durable receipt against both SHA256 and
checkpoint namespace. Managed saves are atomic. The partial-update guard now
covers optimizer, league and replay finalization, not just the PPO function.

## Semantics and limits

This is **statistical continuation**, not bitwise equivalence to an uninterrupted
worker process. A fresh durable namespace intentionally selects a new independent
deterministic deck stream at every launch, including an interrupted launch.
The legacy source lacks serialized main RNG and is explicitly marked as a legacy
bootstrap; later managed checkpoints preserve it. Worker action RNGs and in-flight
rollout state are not serialized. No skipped indices are counted as hands.
Known interrupted executions remain in their attempt evidence; an unknown crash
suffix must remain unknown, not silently treated as zero or added to training.

The CPU diagnostic deliberately changes opponent configuration and workload. It
qualifies recovery mechanics, not policy strength or production GPU throughput.
The already-existing multi-env8 throughput result should be reused as the starting
point of a bounded current-recipe qualification, not a new broad parameter search.

## Remaining work at the safe boundary

1. Verify Seed3 and its sequential launcher finished; freeze all endpoints and
   preserve final raw accounting. Do not alter any prior checkpoint or session.
2. Compare production source to the preserved SHA; if it changed, investigate
   overlapping work before applying the reviewed candidate diff.
3. Apply the candidate changes to production and run the full proportional
   regression suite plus a bounded current-recipe GPU managed resume check.
4. Keep the original 4M evaluation contract and all three seeds. Preserve generic
   audit failures, investigate unrelated integrity issues, and interpret known
   Seed2 training-deal reuse under resume_deviation_amendment.md. No fake passing
   preflight and no automatic 8M promotion.
5. Finish this integration experiment only after actual production integration
   and verification. It remains RUNNING while waiting for that safe boundary.
