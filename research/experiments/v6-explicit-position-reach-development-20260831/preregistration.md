# Explicit-position reach-target development adapter

Evidence fixed before training: parent metric-aligned development review selected
unweighted-TV endpoint SHA256
01049fb680c2f675193e7e73b1bd08d8283ecbfcb21d34f20e49428cf4f05697
but failed its0.19 gate at heroTV0.191491. A post-review descriptive split on the
same development evidence found direct-TV actor1 TV0.2882 preflop and
0.1968/0.1529/0.1746 postflop, versus actor0 0.2057 and
0.0838/0.1066/0.1220. This motivates explicit seat representation; it is not
confirmatory evidence.

Reuse the exact old262144 reservoir observations/IDs, reach targets and derived
actor identities. Append absolute physical seat as extra_info feature3. Start
from the frozen direct-TV endpoint, instantiate the already-qualified
position_adapter_hidden=128 network contract with two seat-specific learned
adapters, and copy every86 base tensor bitwise. Adapter final layers begin at
zero, so epoch0 must reproduce the source probabilities. Freeze all86 base
parameters including value; train only the8 position-adapter tensors.

Fixed optimization: direct probability-TV, NEW Adam1e-4,batch1024,clip1,
8epochs/2048steps, permutation/init seed2026102601. No auxiliary loss, base
unfreezing, epoch rescue or other width. Save epoch08 only. No new environment,
Slumbot or network hands.

Reuse the parent8192 cohort only as a development set, append its preserved
absolute actors, and compare source versus epoch08 per-hand hero TV. Gate:
paired source-minus-treatment95% lower>0, treatment mean<=0.17, and mean
improvement>=0.01 -> FREEZE_POSITION_ADAPTER_FOR_UNTOUCHED_NATIVE_VALIDATION.
Otherwise POSITION_ADAPTER_DEVELOPMENT_NOT_PROMISING. This selection-biased
development result cannot admit strength testing. A pass only admits a
separately preregistered untouched native cohort for this single endpoint.
CPU-scalar/CPU-batch/GPU-batch qualification on64 preserved native states must
also prove the new checkpoint/deployment position feature path; these queries
add no hands.

