# Fixed80k external development comparison: completed review

All32 preregistered2500-hand sessions completed with exit0. Both frozen models
completed40,000 fresh Slumbot hands under the unchanged CPU greedy/legacy-v4 bridge.
Full-model replay passed for125,083 static and122,391 moving decisions. Per-arm
independence checks and cross-arm/prior-token and visible-stream checks passed.
These checks do not prove arbitrary server-RNG or temporal independence.

The exact controller and all37 tracked children are terminal. Independent raw
reaggregation, integer sum/sum-of-squares statistics, raw/audit SHA checks and
historical same-contract comparisons passed. No sessions were replaced, retried,
extended or selected from intermediate scores. New training hands:0; development
evaluation hands:80,000; final-qualification hands:0.

## Results

| Frozen endpoint | Hands | bb/100 | Raw nominal95% CI | Session t15 nominal95% CI |
|---|---:|---:|---:|---:|
| Static8.395M | 40,000 | -19.8721 | [-34.8451,-4.8991] | [-38.2546,-1.4896] |
| Phase-held8.395M | 40,000 | -29.4744 | [-46.5176,-12.4312] | [-52.9146,-6.0342] |

The primary moving-minus-static contrast is -9.6023bb/100:

- Raw independent Welch95% CI[-32.2884,13.0838]; Bonferroni-three adjusted
  interval[-37.3121,18.1075].
- Session Welch95% CI[-38.2127,19.0081]; adjusted[-45.1603,25.9557].
- Four balanced-wave differences are[22.5668,7.1272,-74.6050,6.5018]. Their t3
  sensitivity interval is[-79.5644,60.3598]. Retain every wave. The negative third
  wave drives the aggregate direction; this is not evidence that it is invalid,
  nor a justification to discard its outcomes or favor the three positive waves.
- Seat0 difference -14.9625,95% CI[-41.8501,11.9251]; seat1 -4.2421,
  CI[-40.7905,32.3063]. Each model has exactly20,000 hands per seat.

The ordinary absolute intervals are negative. The more conservative adjusted
session intervals cross zero (static[-43.1040,3.3598], moving[-59.0983,0.1495]);
do not claim a dependence/multiplicity-robust negative effect from every analysis.
Neither policy has a positive sample mean or meets the benchmark goal under any
reported analysis. A method winner and stable profitable learned policy remain
unproven. Static has3/16 positive sessions, moving4/16; these are descriptive counts.

## Internal/external translation and historical context

The final internal moving-minus-static contrast was+14.9470, nominal95% CI
[-5.2945,35.1886]. The external point direction differs, but both method contrasts
remain uncertain. This is not confirmed translation, and not a resolved broad
external reversal. Do not select or reject an entire long-horizon family based on
point signs alone, or equate small Standard10 drift with poker strength.

Relative to the historical same-contract original4M20k cohort (-41.3116), static
is+21.4395, raw Welch95% CI[-5.2229,48.1019], and moving+11.8372,
CI[-16.0404,39.7148]. Relative to same-contract Standard10(-24.5683), the differences
are+4.6962,CI[-18.9276,28.3200] and-4.9061,CI[-29.8933,20.0811]. All include both
sources' sampling uncertainty and are temporally confounded historical context,
not contemporaneous randomized controls or demonstrated improvements. Do not use
historical Standard10 -11.4275 as this test's matched baseline.

## Cost, provenance and decision

Controller execution through analysis took3004.625seconds (50.08minutes), excluding
its subsequent final artifact-index writes and researcher review. Experiment wall
time includes preparation and review and is separately recorded by the logger.

Independent report: `post_terminal_review.json`, SHA256
`0ca3eff30cd967690d6099f2e7a36e4095a822953b6a1236c32800c53dd54d05`.
Models remain static SHA41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372
and moving SHAb0ab97e76dd6d3603b5b6cde0b2fccaa1726fb8b825b23458f9f9f58dc36f932.
This comparison does not erase the training parent's explicitly unknown crash
suffix or convert matched initialization into independent training seeds.

Decision: finish this complete development record without extending it. Do not
promote either model to formal100k qualification or automatically double Seed1
training to16M. Prioritize a separately preregistered, matched two-stage continuation
of the unaffected original Seed3 4M parent, static versus phase-held reference,
to obtain independent-seed geometric evidence at the SAME per-policy dose. This
is uncertainty-reducing replication, not a claim of established external alignment.

The reason to fund replication is the unresolved method contrast, no demonstrated
broad external collapse, the earlier internal signal and feasible measured cost;
the reason not to scale dose yet is the flat/uncertain later curve and unconfirmed
external transfer. Before launching, verify Seed3's actual parent/checkpoint/RNG,
optimizer/replay, assignment and deal provenance and qualify only the necessary
seed bindings. Preserve all historical and current evidence. A later scale or
external-calibration decision must use the combined seed evidence and uncertainty,
not a lucky individual endpoint. No Slumbot-specific rules or action-label training.
