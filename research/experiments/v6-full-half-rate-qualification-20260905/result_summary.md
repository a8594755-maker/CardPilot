# Half-rate qualification passed; no poker-strength claim

Both retained full-network endpoints passed24 unit tests and actual serialized
model/Adam same-gradient fixtures. All86 optimizer moment/clock states, weights,
replay, main RNG, league and counters are preserved. The exclusive derived copies
change only actual LR from9.999999999999996e-05 to4.999999999999998e-05 plus
explicit provenance. No updated fixture models were saved.

Seed1 derived SHA:d9e029c30e58a9d0e3ca81f83bb5ee54103b7044bde359019b4b616384feacd7.
Seed3 derived SHA:f3c2c58a8427896042d4dc0ea90ecc7eea9e5f1952018437f10c7e5ad9e8e3eb.
Identical-gradient parameter-displacement norm ratios:0.50000021894 and
0.50000017585; all86 moment states were bitwise identical between arms after
the fixture, and every clock advanced exactly once. Float32 rounding explains
small displacement deviations; this does not establish actual PPO dose equality.

Qualification report SHA:
afe2955b7a5fd1d257cf0dbd66a86d703f9023315034855e7449515f33fa028b.
Actual-parent qualification wall time14.172s;24 unit tests3.63s. New environment,
evaluation, Slumbot and final-qualification hands are all zero.

Unchanged production trainer source restores Adam group LR and guards the only
decay assignment with --preserve-resumed-optimizer-lr. Actual initial checkpoint,
trace-prefix, managed namespace and worker termination audits remain required
in the separately preregistered continuation. The qualification admits that
experiment only; no stronger policy, external gain or final-goal claim follows.
