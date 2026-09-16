# Backend-stable flattened-sequence residual development

The Transformer residual improved the fixed development cohort from the frozen
explicit-position source TV 0.171099 to 0.157447, and fixed continuation reached
about 0.152805, but the continuation failed both its original development gate and
a full-cohort backend materiality diagnostic. This experiment does not reuse or
qualify that endpoint. It tests whether the useful information is the complete
ordered action tensor rather than attention itself.

Load frozen explicit-position checkpoint SHA256
3b33549547bd1792f2a17b8981976ce560247f787ebd0d2ca1cf837e80ed9526. Freeze every
base tensor. Flatten the existing 25x4x5 action tensor, encode it with a fixed
500->512->256 ReLU MLP, concatenate the frozen normalized 256-wide base trunk and
seat one-hot, and train two seat-specific 514->128->9 residual experts. Initialize
each final residual layer to zero. Train only this adapter for exactly eight epochs
and 2048 Adam steps at lr1e-4, batch1024, seed2026103001, direct unweighted legal
action TV against the same 262144 old phase2 own-reach targets. No early stopping,
extension, rescue, new environment hand, strength hand, Slumbot hand or network.

Use the same preserved 69516-state/8127-hand development cohort once at the fixed
endpoint. Development passes only if paired source-minus-treatment CI95 lower>0,
mean improvement>=0.005, and treatment mean heroTV<=0.15. Independently infer the
entire endpoint cohort on CPU and GPU. Runtime parity passes only if max absolute
probability delta<=2e-5, mean per-state backend TV<=2e-6, greedy disagreement=0,
and fixed-uniform sampled disagreement=0 using seed2026103002. Both development and
runtime parity must pass -> ADMIT_FLAT_SEQUENCE_RUNTIME_INTEGRATION. Otherwise
FLAT_SEQUENCE_DEVELOPMENT_NOT_PROMISING. A pass only admits a separate production
loader/parity experiment and then untouched native validation; it is not strength
evidence and cannot admit Slumbot.
