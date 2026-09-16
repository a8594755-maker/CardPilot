# Matched flat-sequence reward pilot

The production integration smoke preserved Standard10 at initialization, trained
35546 physical v6 hands with valid session/model/optimizer evidence, and scored
+4.8445bb/100 versus v6 source anchor0 over4096 fresh mirrored pairs, CI95
[-13.2092,+22.8982]. This is non-catastrophic but inconclusive and admits one
matched scale-up, not confirmation or external testing.

From the same frozen legacy Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428,
train sequential fresh v6 arms with reset optimizer/counters and identical
seed20261033, worker seed2026103300, fixed deal stream, five fixed learned anchors,
adaptive opponent allocation, sampled hero/selfplay0.25, lr3e-5, PPO2,
target-KL0.01, advantage clip3, source KL0.01, entropy0.005/floor0.05, workers12,
multi8 and exact physical target262144 each. Control updates existing postflop and
preflop policy heads plus critic via all-policy-heads-only. Treatment updates only
the14 zero-output flat-sequence tensors plus critic. No endpoint selection,
continuation, replay or outcome-dependent stopping.

After both terminal session audits pass, freeze final control/treatment and source
anchor0 before evaluation. Evaluate source, control and treatment against the same
five frozen anchors on4096 mirrored pairs per cell at seed20261034, using common raw
decks:15 cells,122880 evaluation hands. The independent unit is the mirrored pair.
For each pair average treatment-control differences across five anchors; likewise
average treatment-source differences. Treatment passes only if both ordinary95%
paired CI lower bounds are >0 and at least3/5 individual treatment-control anchor
point estimates are positive. All input/source-copy/checkpoint/session/physical/
optimizer/raw-deck audits are mandatory. Only treatment can pass to a separate
training-seed confirmation. This known-anchor internal gate is neither Slumbot nor
general strength proof; Slumbot hands=0.
