# Durable attempt namespace: validated contract, production integration pending

This bounded infrastructure experiment replaces an unsafe assumption (restored
counters imply new worker deals) with a durable, single-use attempt namespace.
No live production source, checkpoint, optimizer, replay, or session was changed.

`fixed_deal_attempt.py` reserves a UUID namespace using exclusive file creation
and fsync before workers may start. A crash or torn receipt consumes that name;
it is never silently reused. The deterministic v2 deck key includes namespace,
worker seed, environment index and deal index. Existing empty-namespace v1 deck
generation remains exactly reproducible for historical evidence. Allocation does
not increment any hand counter. This is statistical continuation, not bitwise
uninterrupted training, and is not a claim of power-loss-proof storage.

## Evidence

- 12 attempt-contract tests: durable hash-bound replay, exclusive allocation,
  concurrent claims, deliberate child-process exit after fsync, torn/tampered
  receipts, namespace separation, v1 parity and physical-v6 reset replay.
- 13 earlier overlap tests, including randomized exact set/interval comparison.
- 26 existing optimizer/replay/reference/gradient/pool tests plus four logger
  tests. Combined command: 55 tests passed.
- Real single-env and two-env workers completed 16 CPU validation hands, with
  16 independent reference replays. Observation, action, terminal reward,
  complete transition-block and physical counter checks all passed.
- Same worker seed/env0/deal0 produced different decks across durable attempts.
- The production trainer SHA stayed
  `594f1de70f9a6abdf8076fe129a18056b5a3bd84087ad4f6cc2f1498850a6956`.

The real-worker probe uses dependency injection in newly spawned diagnostic
interpreters. It is evidence for the worker/deck contract, NOT evidence that the
production CLI has already been integrated. No learned training hands, policy
evaluation hands or Slumbot hands were generated; diagnostic physical hands
remain a separate accounting category.

## Safe-boundary integration requirements

1. Reconfirm the entire current sequential training launcher is terminal, not
   merely that its Seed2 child changed to Seed3. Preserve final outputs first.
2. Wire namespace selection into both worker paths and their raw deal identities.
   Reserve before worker startup; persist namespace and receipt SHA in config,
   checkpoint and manifest. All future managed attempts use a fresh receipt.
3. Keep the training seed and inherited weights/optimizer/replay counters intact.
   Document the new v2 stream contract and statistical continuation explicitly.
   Do not graft this onto the running preregistered4M experiment silently.
4. Verify a tiny genuine trainer start/save/interruption/resume cycle on CPU,
   including optimizer step, replay RNG, parent SHA and zero overlapping attempt
   identities. A same-namespace live allocation must fail before worker creation.
5. Update generic evidence auditors to distinguish namespace-based freshness,
   legacy cursor-window evidence, actual physical work and unique coverage.

## Next resource decision

The existing 2026-08-31 GPU throughput experiment already qualified multi8 for
fresh starts. Reuse that evidence; do not repeat its original search. Any future
throughput confirmation should specifically test the current replay/adaptive
league/heads-only recipe and managed resume contract. Do not confuse its
collection-only `hands_per_second` with end-to-end physical hands per wall second.
