# Matched corrected-v6 learned-opponent diversity pilot

## Evidence and hypothesis

The corrected-v6 three-anchor full-network curve specialized toward its training
opponents. Increasing source KL0.01 to0.1 reduced common-state drift but failed
the held-out strength-retention gate. Neither prior final is eligible for external
promotion. The next intervention changes training opponents, not action rules.

The real-GPU throughput experiment qualified fresh-start12workers x8environments
with intact stream/accounting/numerical evidence. Its three short-run policies are
ineligible here. Source tensors remain original Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.
Hypothesis: exposure to two stronger, differently regularized v6 learned policies
reduces three-anchor specialization and improves held-out performance relative to
a newly trained matched three-opponent control.

## Fixed training

Run control3 then diverse5 sequentially, each from original source tensors with
new v6 binding, fresh Adam/counters/run ID, target262144 actual terminal hands at
the first complete PPO-update boundary. Include and report overshoot and completed
unconsumed tails. Never resume short throughput arms or either old learning final.
Seed20260926; worker seed base2026092600, fixed per-slot deck streams from index0.
Matching seeds do not imply identical asynchronous trajectories or counts.

Use the qualified multi8 command and unchanged learning configuration: full86tensor
network, source KL0.01 to bound source anchor0, LR3e-5, PPO2epochs/targetKL0.01,
4096 legacy marker collection, minibatch1024, GN critic_v2/valuecoef1, entropy0.005,
advantage clip3, 25% self-play, adaptive per-group assignment8groups, EMA0.9,
temperature2, probability floor0.05, no deliberate inference accumulation,
validate-stream, archive every4updates/save every update. Runtime safety cap3600s
per arm; no automatic retry or interrupted multi-slot resume.

Control fixed pool is anchor0/1/2 from v6-full-network-learning-curve-20260831.
Treatment appends exactly two frozen training opponents:

- Previous v6 KL0.01 final SHA256
  0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606.
- Previous v6 KL0.1 final SHA256
  9b7b0e3a0c2be3bdfbbab4167e1eb4a5e7f284d619a8afa13d608c9943b46efb.

Both are training opponents only, not candidates. The only between-arm learning
intervention is this pool expansion and its consequent adaptive allocation.
Source initialization/reference, sampling, architecture and all other settings
are matched. Fixed pool membership avoids unqualified mid-hand dynamic pool
replacement. Evaluation anchors3/4 are not in either training pool.

## Fixed evaluation and joint gate

Freeze both new finals before strength evaluation. Evaluate source, control3,
diverse5 against anchors0..4 on8192mirrored pairs per cell, seed20260927: exactly
245760 new internal physical hands. All15cells share full deal sequence and keyed
action uniforms; use CPU6 concurrent evaluators,1torch thread each, below-normal
priority. No training/evaluation overlap. Complete all cells without optional
stopping, no alternative seeds or intermediate checkpoint promotion.

Primary family has six contrasts: diverse5 minus source at each of five anchors,
plus the within-common-pair mean of (diverse5 minus control3) across held-out3/4.
The independent unit is a mirrored deal pair, not a state or individual seat;
compute mean/SE from raw pair JSONL. Report ordinary95% intervals and Bonferroni
six-contrast simultaneous95% intervals (two-sided z at1-0.05/12).

Only diverse5 may pass to a separately preregistered independent confirmation:
all five source-difference point estimates positive; at least three adjusted
lower bounds positive including source anchor0 and at least one held-out anchor;
held-out diverse5-control3 adjusted lower bound positive. Mandatory full source,
checkpoint, session/RNG chain, physical counter, optimizer/numerical and raw deck/
arithmetic audits must pass. The control is diagnostic only; no fallback promotion.
This internal gate never establishes Slumbot or Nash strength. Old held-out
families have influenced prior research, so this is not an unseen-family or
multi-training-seed causal claim. Require independent future evidence before any
external admission. Slumbot hands=0 in this record.

## Provenance

Qualified throughput execution.json SHA256
2f1da801ec637ef4c5ce4fcf03b8a1170d40020502b4f774f1bb6835e13389e7,
reviewed_analysis.json SHA256
20c2669a14cb51f9231b9c416e2de19ae5049c23d5837c06efb639998f494fde.
Capture exact expanded commands, source SHA/patch plus source copies, frozen
identities, contiguous metrics/assignments, terminal session audits and raw pairs.
Update RUNNING accounting from manifests/raw evidence; preserve any failure.
