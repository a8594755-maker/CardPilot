# Flattened-sequence residual fixed continuation

The frozen-base flat-sequence parent completed exactly eight epochs and 2048 Adam
steps with every epoch mean training TV decreasing (0.147198 to 0.136472). Its full
development endpoint improved the explicit-position source by 0.014468 with paired
CI95 [0.013635,0.015301] and passed full-cohort backend parity, but mean heroTV
0.156631 missed the fixed 0.15 gate. This learning curve justifies one new-record
fixed convergence continuation, not a same-record extension.

Load exact parent SHA256
32e491e0967e097ef77ce036d6441cd466260c136453b2d53e5f9f46ee8e68ba, including
its flat_sequence_residual_v1 adapter and Adam state at step2048. Do not reset any
parameter or optimizer state. The parent did not serialize numpy generator state;
reconstruct default_rng seed2026103001 and advance exactly the eight complete
262144-row permutations already consumed, then train fixed epochs9-16 / steps
2049-4096 at unchanged lr1e-4, batch1024, direct unweighted legal-action TV. No
early endpoint inspection, stopping, rescue, retry or further extension. Zero new
environment hands, strength hands, Slumbot hands or network.

At the fixed endpoint only, recompute the same preserved 69516-state/8127-hand
development cohort against the original explicit-position source. Development
passes only if paired source-minus-treatment CI95 lower>0, mean improvement>=0.005,
and treatment mean heroTV<=0.15. Full-cohort CPU/GPU parity independently requires
max probability delta<=2e-5, mean per-state backend TV<=2e-6, greedy disagreement=0,
and fixed-uniform sampled disagreement=0 using seed2026103002. Both pass ->
ADMIT_FLAT_SEQUENCE_RUNTIME_INTEGRATION. Otherwise
FLAT_SEQUENCE_CONTINUATION_NOT_PROMISING and stop this supervised residual route in
favor of full sequence-policy reward training. A pass is development-only and can
only admit a separate runtime integration and untouched native validation.
