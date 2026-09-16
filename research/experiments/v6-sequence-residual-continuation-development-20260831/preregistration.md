# Sequence-residual fixed continuation development

Parent sequence residual SHA256
96913cf9ae4a0574ab2e5f95bc93abd4b39fdad43395a7882050cc95781172b2
completed8epochs/2048steps at development heroTV0.157447, improving source by
0.01365 but missing0.15. Preserved per-epoch training-TV means decreased every
epoch from0.14639 to0.13690. This motivates one prespecified continuation, not
an in-record rescue.

Load the exact parent adapter and Adam state at step2048; do not reset either.
Reconstruct its numpy permutation generator from fixed seed2026102801 and
advance exactly eight full262144-row permutations, then train epochs9--16
(2048 additional steps; final total4096) on the same old reservoir/targets with
the identical direct-TV,batch1024,clip1. Base3b335 policy stays fully frozen.
This parent did not serialize numpy state/order digests; deterministic
reconstruction from captured code/seed is an explicit limitation and is
independently checked, not claimed checkpoint-native resume.

Evaluate only epoch16 on the same known development cohort. Gate: paired
epoch08-minus-epoch16 heroTV95% lower>0, improvement>=0.005 and epoch16 mean
<=0.15 -> ADMIT_SEQUENCE_RUNTIME_INTEGRATION. Otherwise
SEQUENCE_CONTINUATION_NOT_PROMISING. No epoch9--15 evaluation/rescue, no further
automatic extension. Preserve optimizer step4096, all adapter tensors, base
hash, CPU/GPU parity and exact rows. Zero new hands/network/strength evidence.
A pass only admits production-loader integration and untouched native
validation, never direct Slumbot.

