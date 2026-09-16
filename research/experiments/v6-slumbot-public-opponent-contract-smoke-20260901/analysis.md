# Public opponent execution-contract smoke analysis

The frozen public model and Standard10 checkpoint completed two identical
seeded 2,048-hand cohorts.  Their logical trajectory JSONL files had the same
SHA256, and all 5,918 opponent decisions replayed with identical action and
street counts.  Every action was selected from the exact physical-v6 legal
mask.

Coverage included every street, fold, call/check, and four distinct raise
slots.  Replacing the model actor's actual private cards on 256 visited states
changed no action probability, confirming that the runtime honors the
public-only feature contract rather than leaking simulated hole cards.

Standard10 scored `+97.7959 bb/100` against the model on the unique 2,048-hand
cohort.  This is not an external-strength estimate: the model marginalizes
Slumbot behavior from Standard10-generated histories and is deliberately not a
full-information poker policy.  The positive score shows that it is an
exploitable behavioral opponent, so allowing it to dominate training would
risk narrow best-response overfitting.

Decision: `ADMIT_PUBLIC_OPPONENT_WORKER_INTEGRATION`.  Integrate it only as a
bounded minority identity in a fixed diverse league and compare against an
otherwise identical control.  Preserve Standard10 initialization and use
untouched learned-policy anchors; do not imitate its actions into the hero and
do not allocate fresh Slumbot hands at the integration-smoke stage.
