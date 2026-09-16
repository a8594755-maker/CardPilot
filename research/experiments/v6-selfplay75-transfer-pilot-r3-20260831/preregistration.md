# Matched corrected-v6 self-play share transfer pilot r3

R3 also corrects test fixture extraction of the allocator metadata.groups list.
R2 had10passing/3failing pretraining tests and zero trainer children/hands.
R1 andR2 originals/evidence stay untouched. Production trainer/settings are
unchanged; only test harness defects corrected, new r3 run IDs and directory.


Registered before new training. Supersedes v6-selfplay75-transfer-pilot-20260831, which failed
pytest collection before any trainer child or production directory existed.
Zero training/evaluation/network hands were generated. All first-attempt source
and evidence remain unchanged. This separately logged r2 corrects only the test
harness sibling-module import path, uses new r3 run IDs, and reuses the still
unconsumed preregistered seeds/settings. This is not a retry of training data. The physical1m final improved all five internal
anchors on independent confirmation, but its valid fresh20k Slumbot pilot scored
-137.73925bb/100, raw95%CI[-183.1154648,-92.3630352], session95%CI
[-182.1363194,-93.3421806]. No100k admission or extension of that policy.
External review SHA256
3ed7b4efe7abdd789221a8dda96c0c3d47ca2516f41aa6d6f97f9065f64febbb.

The specific hypothesis is that excessive exposure to three fixed old opponents
encourages narrow exploitation. Increasing current-policy self-play exposure may
improve transfer. This is a hypothesis, not an established cause of the external
loss. The [AlphaHoldem paper](https://cdn.aaai.org/ojs/20394/20394-13-24407-1-2-20220628.pdf)
describes self-play against historical versions and an opponent pool for sampling
diversity. This experiment does NOT reproduce its K-best algorithm: local dynamic
pool replacement is not yet qualified for mid-hand identity, so membership stays
fixed and only the self-play share changes. No Slumbot actions/trajectories enter
training and no benchmark-specific action rules are added.

## Matched new learning

Run control25 then selfplay75 sequentially. Both initialize ORIGINAL Standard10
tensors SHA25691b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428
with explicit fresh v6 binding, new Adam, zero NEW counters and distinct run IDs.
Neither resumes or promotes any failed old candidate. Unknown old physical-hand
prefix is excluded from all new accounting. Learner seed20261005, worker seed
base2026100500, per-slot fixed deal start0 for both. Matching seed settings do not
imply identical asynchronous trajectories or identical optimizer-update counts.

Each arm target1,048,576actual terminal environment hands at the first complete
PPO-update boundary, about2,097,152total plus declared overshoot. Report shutdown
tails, both-player collected transitions, updates/Adam steps and realized self-play
assignment exposure separately. Runtime cap7200s per arm, no automatic retries,
interrupted multi-slot resume, dropped-prefix recovery or continuation from an
old short-run policy.

Qualified12workers x8environments, CUDA,4096legacy collection markers,
minibatch1024,LR3e-5,PPO2,targetKL.01,source-policy KL.01 to anchor0, full86tensor
GN critic_v2,entropy.005/floor.05,advantageclip3,valuecoef1,validate-stream,
save every update/archive every4updates,no inference accumulation,no replay.
Fixed adaptive pool anchors0/1/2;8assignment groups,EMA.9,temp2,floor.05.
Only arm difference: requested self-play group fraction .25 versus .75.
This means2of8 versus6of8groups, not exactly25%/75%of physical hands because
groups contain unequal worker counts and action/throughput distributions differ.
Those induced differences are part of the intervention, not separately identified
causal effects. Current-policy self-play uses the learner on both seats.

## Fixed internal diagnostic, no surrogate-strength selection

Freeze source and both new finals before any strength evaluation. Exactly
3candidates x5anchors x4096mirrored pairs x2seats=122880new internal hands.
Seed20261006, shared full52card decks and keyed seat/action uniforms across cells,
CPU6concurrent1thread,below-normal priority. Anchors3/4 never enter training but
are known families, not unseen-family holdouts. No training/evaluation overlap,
outcome peeking, alternate seeds, midpoint promotion or sample extension.

Prespecified descriptive family: selfplay75-source at each of5anchors and the
within-common-pair mean(selfplay75-control25) on3/4. Report ordinary95% and
Bonferroni family6 simultaneous95%CIs from raw pair averages. Also report all
absolute cell means. These internal results are diagnostic and MUST NOT decide
which arm receives the external transfer test, because prior internal success
did not transfer. No claim of general strength from these CIs alone.

## Prespecified next experiment

If BOTH new arms pass health/accounting/session/frozen/raw-evidence checks,
admit BOTH exact finals to one separately logged fixed external transfer pair:
20000fresh Slumbot hands PER ARM,8x2500sessions each, balanced/interleaved arm
launches at total concurrency8, regardless of internal ranking. Complete both
arms without optional stopping or substituting models. Candidate-specific
deployment parity is mandatory beforehand. The later external record must
preregister fresh IDs/seeds and an independent between-arm raw/session contrast
before any requests. Nothing external launches from this wrapper.

A positive external point with valid evidence can admit separate fresh100k
qualification; if both are positive, preregister selection by the larger20k point
estimate with a fixed tie-break(control25). External pilot/internal samples may
not be pooled into qualification. If neither is positive, neither qualifies.
The Goal remains SAME frozen policy>=100000fresh Slumbot hands, positive bb/100
AND95%CI lower>0, not an internal or20k result. No automatic4M/2.7Bscale-up.

If an arm fails infrastructure/health, preserve all artifacts; do not rescue the
survivor by changing this paired design after observing outcomes.

## Provenance

python research/experiments/v6-selfplay75-transfer-pilot-r3-20260831/run_pilot.py

Reuse the qualified multi8 command from v6-gpu-multienv-throughput-20260831;
execution SHA2562f1da801ec637ef4c5ce4fcf03b8a1170d40020502b4f774f1bb6835e13389e7,
review SHA25620c2669a14cb51f9231b9c416e2de19ae5049c23d5837c06efb639998f494fde.
Capture own exact source copies/hashes/dirty patch and expanded commands. Execute
trainer, evaluator and session auditor from the captured source tree. Preserve
all prior copies/evidence and current-run originals unchanged. Continuously log
actual terminal counters and complete raw lines. Wrapper stops at
COMPLETED_PENDING_REVIEW; independent review finishes this same record.
