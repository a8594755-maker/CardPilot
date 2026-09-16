# Sequence-continuation backend materiality diagnostic

The parent fixed continuation completed every training step and preserved endpoint
SHA256 0c23549877cc01c5f46fa8f24ede31c7806a0d29bfc696054042864f54c7c9ac,
but correctly FAILED before analysis because its64-state CPU/GPU max probability
delta exceeded the preregistered2e-5 gate. This diagnostic never changes that
status or retroactively qualifies the endpoint.

On all69516 preserved development decision states, compute frozen CPU and GPU
probabilities from the exact endpoint and independently compare max absolute
delta, mean per-state TV, greedy-action disagreement, and sampled-action
disagreement using fixed per-row uniforms from seed2026102901. Recompute the
per-hand heroTV and original epoch16 development gate on each backend versus
the frozen epoch08 parent. Zero gradients, new hands or network.

Before queries, define bounded numeric drift only if max delta<=1e-4, mean
backend TV<=1e-5, greedy disagreement<=1e-4, sampled disagreement<=1e-4, and
absolute CPU-versus-GPU heroTV difference<=1e-4. All must hold ->
BACKEND_DRIFT_BOUNDED_REQUIRES_EXPLICIT_RUNTIME_CONTRACT; otherwise
BACKEND_DRIFT_MATERIAL. Also report, but do not use to change this decision,
whether each backend independently satisfies the original continuation
development gate (paired lower>0, improvement>=0.005, mean<=0.15).

A bounded result may only motivate an explicit single-backend production
runtime integration with stronger parity tests and a later untouched native
cohort. It does not validate the failed parent, select hands, establish
strength or admit Slumbot.

