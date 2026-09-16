# Joint explicit-position reach-target development fit

Fixed evidence: the explicit-position adapter parent independently changed only
8 adapter tensors, kept86 base tensors bitwise frozen, and improved development
heroTV by0.02039 to0.171099, narrowly missing its0.17 gate. The prior gap
decomposition found no history-truncation concentration and no>0.03
generalization gap. This motivates joint feature adaptation before a new
sequence architecture. It is still development evidence, not strength.

Initialize exactly from parent SHA256
3b33549547bd1792f2a17b8981976ce560247f787ebd0d2ca1cf837e80ed9526.
Reuse the exact262144 old reservoir observations/IDs, reach targets and absolute
actor identities. Preserve explicit extra_info seat feature and128-wide two-seat
adapters. Train exactly88 tensors (80 shared/policy base plus8 adapters), freeze
the6 value tensors. NEW Adam1e-4, direct probability-TV, batch1024,clip1,
8epochs/2048steps, fixed seed2026102701. No epoch rescue, auxiliary loss, width
change, new hands or network.

Reuse the same known8192 cohort only as development. Epoch0 must reproduce the
parent; evaluate only epoch08. Gate: paired parent-minus-treatment95% lower>0,
mean improvement>=0.01 and treatment heroTV<=0.15 ->
FREEZE_JOINT_POSITION_FOR_UNTOUCHED_NATIVE_VALIDATION. Otherwise
JOINT_POSITION_DEVELOPMENT_NOT_PROMISING. The result and intervals are
selection-biased and cannot admit strength/Slumbot evaluation. A pass admits
only a separately preregistered untouched native cohort comparing this single
frozen endpoint to its frozen parent. Qualify CPU scalar/CPU batch/GPU batch on
64 stored native states and independently review all frozen/value/optimizer
identities.

