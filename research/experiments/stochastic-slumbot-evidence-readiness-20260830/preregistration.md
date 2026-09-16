# Stochastic Slumbot evidence readiness

Zero new environment/evaluation/Slumbot hands. No checkpoint or learned distribution changes. Start-state CI tests:3passed. Preserve all historical benchmark evidence and labels; stronger new audits do not retroactively establish that an old run was invalid.

## Required evidence contracts

1. Retain action-dependent full fingerprints and add an initial hero-card/physical-seat fingerprint that cannot change with sampled actions, exposed boards, opponent cards or winnings. Validate card/seat consistency within each hand. Reject3consecutive same-index initial fingerprints; reject >1% same-index initial matches when at least100indices overlap. Search5consecutive initial fingerprints at arbitrary offsets to catch shifted replay without the high collision rate of arbitrary-offset3-card windows at100k scale. Report these as observable replay diagnostics, never a proof of full probabilistic independence.
2. Final audits reject malformed JSONL; duplicate resolved input paths must not multiply evidence. Raw rows require unique contiguous successful/attempted indices for complete clean sessions, finite bounded rewards, integer chip units, chip/bb/cumulative agreement, exact requested/summary/dump hand counts, immutable input hashes and consistent policy identity.
3. Add explicit hand execution-clean telemetry for the existing HTTP/out-of-turn fallback branches. Do not change their action behavior in this readiness experiment. Future pure-policy benchmark evidence rejects any such fallback or missing telemetry. Preserve completed rewards and dump rows even when evidence is invalid.
4. Add an optional explicit policy RNG seed, applied before the first game after model load, with seed/temperature metadata in result JSON. This controls reproducibility, not probabilities; defaults remain compatible. Fixed future sampled-policy tests use native sample/temp1 with no action heuristics.
5. Strict frozen evidence audit also reconciles each observed hero behavior probability vector, selected slot, legality, mode and temperature, plus complete hand/execution/result metadata. A permissive ordinary CI report alone cannot certify a frozen-policy benchmark.

## Tests and closure

Use synthetic independent and deliberately duplicated streams with different actions/winnings/boards, shifted repeated streams, missing cards/indices, duplicate paths/rows, malformed/truncated JSON, invalid numbers, chip/bb disagreement, changed policy/hash, incomplete summaries and fallback telemetry. Include a fixed-seed100k-hand-sized synthetic independent-stream test. Unit tests must call the actual public audit helpers/CLI, not only fixtures. Recheck existing CI/default and relevant client policy/dump tests. A zero-hand CPU loader dry-run is permitted; external API games are not.

Capture the final execution source/patch/hash snapshot separately from the start-state snapshot. Finish this record only after tests and a valid synthetic end-to-end frozen evidence manifest succeed, invalid fixtures are rejected, original Standard10 hash is unchanged, and no external game was played. Then separately preregister the proposed fixed20k sampled baseline; do not launch it as an unlogged smoke test or mix its hands into a later independent formal100k.
