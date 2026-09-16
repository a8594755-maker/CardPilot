# Position-aware sequence residual reach-target development

Fixed source is the independently reviewed best explicit-position adapter SHA256
3b33549547bd1792f2a17b8981976ce560247f787ebd0d2ca1cf837e80ed9526,
development heroTV0.171099. Jointly updating all policy/shared tensors worsened
TV with a fully negative paired interval, so the source remains frozen.

Add one development-only learned residual over the existing native observation:
flatten each of the24 ordered action-event channels to20 features, append the
metadata token, project to128, add learned positions, and use2 Transformer
encoder layers/4 heads/feedforward256/dropout0. Padding event tokens are masked;
the final metadata token attends all observed earlier events. Concatenate its
representation with a LayerNorm copy of the frozen source trunk feature and
absolute-seat one-hot, then apply two seat-specific128-wide MLP experts to9
logit deltas. Both final layers initialize exactly zero; epoch0 must reproduce
the source. No future action, opponent private card or teacher identity enters.

Freeze the entire source policy including its position adapters/value. Train
only sequence residual tensors with direct probability-TV, NEWAdam1e-4,
batch1024,clip1,8epochs/2048steps,seed2026102801 on the exact old262144
reservoir rows/reach targets/actor identities. Reuse the known8192 cohort only
as development, evaluate only epoch08, no epoch rescue/width alternatives.

Gate: paired source-minus-treatment heroTV95% lower>0, improvement>=0.01,
treatment mean<=0.15 -> ADMIT_SEQUENCE_RUNTIME_INTEGRATION. Otherwise
SEQUENCE_RESIDUAL_DEVELOPMENT_NOT_PROMISING. This selected development result
is not strength or confirmation. A pass first requires an independently tested
production loader/external parity implementation and then an untouched native
validation cohort; it does not directly admit Slumbot. Record all optimizer
state, source hashes, row counts, custom CPU/GPU batch parity and0new hands.

