# V5 Takeover Handoff

Checked: 2026-07-14T07:31:00+00:00

## Latest authoritative correction: H8 registered, launch still blocked

H7 remains terminal `FAIL / H7_FAIL_REGISTERED_GATE`. The formal Route Review 004 result
SHA `126dfc461c822c4b2bb4e599ac3da276b6412a9dda210ba8912a8d97fc0a6859` is
`PASS_ROUTE_REVIEW`, `route_exhausted=false`, and selects
`H8_VALUE_HEAD_ONLY_CATCHUP_AFTER_KL_STOP`. Its prerequisite research review's
`PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` status is not the final route authority.

H8 preregistration SHA `ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713`
is immutable `REGISTERED_NO_LAUNCH`. It freezes fresh same-start 20M control/treatment
arms from the exact H7 treatment endpoint with target-KL0.03 and optimizer state
preserved; only treatment enables value-head-only catch-up after KL early stop. Launch
is blocked until implementation, independent audit, design lock, preflight, and canonical
rearm pass. H8 authorizes zero official hands and no strength claim.

No Python trainer, watcher, mirror, or Path-1 process was observed in the live read-only
check. Revalidate the Path-1 no-overwrite job before any resume. Official strength remains
L0:20,400 greedy-direct hands, `-153.2999 bb/100`, CI `[-187.6945,-118.9052]`.

The intermediate route-pivot-frozen section below is historical prerequisite evidence.

## Superseding transition: H7 terminal FAIL, route pivot frozen waiting for evidence

H7 is terminal `FAIL / H7_FAIL_REGISTERED_GATE`. Its fixed40k common-deal mirror passed
at treatment-minus-control `+123.9907 bb/100`, 95% CI `[+98.3343,+149.0737]`, but the
registered endpoint value gates failed: normalized-MSE degradation was `12.2256%` with
bootstrap95 upper `18.6237%`, and treatment KL p95 was `0.03062 > 0.03`. Judgment SHA
`6d0e2ae773ca79c57606d5de6765e67ed2c12aba92be41611f44a2c6ba581304`; immutable audit
SHA `89382ddb7fadd319cd77afb6cad106182735401b1e37034657c67e94466c5027`. H7 may not be
extended, reseeded, reclassified, or evaluated at a later endpoint.

Route Review 004 is `PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` with program state
`TIER2_FROZEN_ROUTE_PIVOT`, SHA
`e8df3c12876aaf1f38cd88a652bc1ca87f42ba4fab3f83235213f2a61a9efef9`. It authorizes
no behavior change, action-specific intervention, official hands, or strength claim.
DRIVE-TO-L5 remains the objective, but execution waits for its named causal evidence;
route exhaustion was not proven.

A read-only process check at `2026-07-14T07:26:03Z` found no Python trainer, watcher,
mirror, or Path-1 process. The last Path-1 immutable recovery artifact SHA
`ef948410dac4b18c0ff14a1e36d39a17868d22a55d5e21c6acb46912b66ec526` recorded a
same-job no-overwrite resume after reboot; absence of a process is not completion proof.
Revalidate identity and progress before resuming it. Official strength remains L0:
20,400 greedy-direct hands, `-153.2999 bb/100`, CI `[-187.6945,-118.9052]`.

The prior H7-running material below is historical and must not override this section.

The standing campaign remains `ACTIVE_DRIVE_TO_L5`. L5 is immutable: a frozen V5-lineage greedy-direct policy must complete 100k+ official Slumbot hands with bb/100 >0 and 95% CI lower bound >0. Official strength is still L0:20,400 hands, -153.2999 bb/100, CI[-187.6945,-118.9052]. H1-H7 internal work authorizes no official hands or strength claim.

## Authoritative live transition: both H7 endpoints frozen PASS, control mirror running

H6 is terminal `FAIL / H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`. It stopped after61 accepted rows at iter31461 /516,992,852; control effective h/s2239.186573 versus treatment1147.971883, ratio0.5126736187 <0.85. Judgment SHA `25950437f46dbda6ec7c07d61db61c9c5630061868769d6723116cd2a2677053`; independent audit SHA `0adcc3326b3934072a31757ba8319839afa7a2346db4c7f3350ce9263518d867` PASS. Partial mirror data is exploratory-only and H6 may not be reclassified.

Route Review 003 preregistration SHA `e1e1dad8c44233527fbd2ebb65725748378b3d93bf6a482e848de393b6c68908` and result SHA `cdf17d3cdaba749cc881e7c48fd37a9a6dbcf3b3aac82cee46473415678d9f99` are PASS_ROUTE_REVIEW,route_exhausted=false. Selection is `H7_FRESH_CONTEMPORANEOUS_AB_WITH_EVALUATIONS_DEFERRED`.

H7 preregistration SHA `45b57f4fe817f1b98e7267a8e482d46b8121fb41d4e432a8af25a1857c6cb4b7`, design lock SHA `88aea213e00614191b79496079ea8607aca67a0a7d9c582f47a93af011f325af`, design audit SHA `bd9eb98b76d65c25a02a20cfb2d23e8d283cb1c27d1d6564efaca91085937869` PASS and preflight SHA `6d9018bec60e0aefdf2dc31b745dd734242cedba056f3bea532a06e51721283c` PASS. Fresh control then fresh treatment each run20M from exact gate31400; sole variable is completed-epoch mean KL early-stop threshold0 ->0.03.

Control `v5_hybrid_h7_control_kl0_same31400_20m_r1_20260713` is frozen PASS at iter32617 /536,005,488, overshoot15,827 within50k; checkpoint SHA `468f7a854e59387f2dda3bef7287a934a31d0ef75a5ec402db18bce02290d71b`. Protocol guards PASS, entropy20 abort false, isolation violations0 and stderr empty. First60 remains frozen at1085.698240 effective h/s.

Exact treatment `v5_hybrid_h7_treatment_kles003_same31400_20m_r1_20260713` is frozen PASS at iter32617 /536,001,286, overshoot11,625 within50k; checkpoint SHA `948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149`. Manifest finished, trainer exited, health/protocol guards PASS, stderr0, entropy20 abort false and isolation violations0. Registered first60 remains PASS: control1085.698240 versus treatment1078.677831 effective h/s, ratio0.993533739.

Reporting-only live control-plane audit SHA `792f9a460ec093f88fd5cb62e3c6121b18e988f6e4f9f581b4392a091bd78537` is PASS18/18. It independently revalidates the design lock, both launcher hashes/final lock binding, control+treatment endpoint/protocol validate-only contracts, completion validate-only, exact first60 recomputation, clean isolation, dormant mirror and official-hands0 without changing any locked tool or process.

A reporting-only dashboard watcher crash was CENSUREd and corrected: the legacy L6 claim audit attempted numeric formatting on H7 checkpoint `config.total_hands=null`, leaving progress stale while trainer/health/endpoint/protocol watchers continued. The formatter now renders missing counts as `unknown`; tests3/3, py_compile and a live `L6_NOT_PROVEN` audit pass. Canonical rearm restored all eight permitted watchers with survival PASS and empty dashboard stderr. Artifact `reports/v5_h7_dashboard_reporting_correction_20260713.json`; H7 gates and verdict authority are unchanged.

Control freeze/treatment launch artifact SHA `c81b53dcb2a6e1c80efa12f6f98cc5e0d53e7e59025a5c03768ca81e0ba53564`. A launch-status ancestor race was CENSUREd: canonical rearm ended the invoking watcher after the exact treatment trainer and replacement watchers were healthy. Duplicate-safe reconciliation selected `TREATMENT_ALREADY_LAUNCHED` and did not invoke a second launcher. No behavior or verdict effect.

Both endpoints are now frozen PASS and no trainer remains. Completion watcher launched the fixed40k control mirror as PID20552,CPU-only/BelowNormal,threads1/inter-op1,manifest SHA `57d43cb5ca58690d6f532c565badb0ff831d1d26cf1e94de9385c5cbc4028028`,measurement-lock SHA `8d5b9ab7c6011a2fdd17b013379c8ae3c5c3c904aa61e271cc0166f872562c75`. Transition artifact SHA `593783824e2fb1ab7d4bdd33025ef39091375dbbc7040f4e1fa65ee1e3b09670`. The duplicate-safe chain is control mirror,treatment mirror,audit,mirror judgment,H7 terminal judgment. No official hands.

No endpoint evaluation,mirror or Slumbot may run while either H7 trainer is active. The duplicate-safe watcher launches treatment only after the control endpoint/protocol freeze PASS. H7 mirror manifest SHA `57d43cb5ca58690d6f532c565badb0ff831d1d26cf1e94de9385c5cbc4028028`, lock SHA `8d5b9ab7c6011a2fdd17b013379c8ae3c5c3c904aa61e271cc0166f872562c75`; it remains dormant until both endpoints freeze PASS and no trainer remains.

## H2 terminal state

H1 is terminal FAIL and critic_v1 gate31400 remains the exact H2 source. H2 preregistration v2 SHA `aaf8bf30db6e757e15c1b9ae1bdd0b5e3eed379ec1dadbd23b2d8a70b1f2fa2f`; design lock SHA `f4526c4175130857f34b2669a629f5a1c80410e15f32ba5975ccc7c580876c75`.

Control `v5_hybrid_h2_control_allinonly_same31400_20m_r1_20260713` is frozen PASS at iter32616 /535,989,948, checkpoint SHA `f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b`. Manifest finished, exact health/protocol PASS, stderr empty; first60 is frozen at2239.1866 effective h/s.

Treatment `v5_hybrid_h2_treatment_showdownk200_same31400_20m_r1_20260713` was automatically terminated at iter31461 /516,993,062 by the registered first60 throughput guard. Control effective h/s2239.186573, treatment1202.764735, ratio0.5371435994 <0.85. Terminal judgment SHA `947f7f73ac9f1ace08581f42f223b855e46f20732bd7de69a3d2c175c7d5eae7` is `FAIL / H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`; independent audit SHA `494bb3bcb045f552e504e2313c679e68b149a905c270b7243363c120d2815515` PASS. Completion audit SHA `0374827b98a94cd580eadf2437d3882d9ccdf21b1e40e236212046575ebd972a` is PASS_COMPLETE_H2_TERMINAL_FAIL_PROTOCOL_ABORT. Treatment is rejected; gate31400 critic_v1 remains the route source.

Endpoint MSE,treatment endpoint/treatment mirror,full-window throughput and terminal entropy were not run after abort. Partial control mirror stopped at7896 rows SHA `f5706ca2f724d7f01614930cb5bffbf6c3b6ebc782875eb9f736ec5a85fabf60` and is exploratory-only. Launch-status and completion-supervisor protocol-branch omissions were CENSUREd as reporting-only; neither changed the registered verdict.

Mirror measurement lock SHA `800c0b75e70ab5dedb54c853956d27333598f1e9ddcf6fa85162ad59e0921618`; terminal judgment lock v3 SHA `f776d11bb01ed44a8d386ba31cce335be66b742f83e8c6a6de07451ca3003d9a`, audit PASS10/10. A valid H2 FAIL or fixed-sample INCONCLUSIVE after H1 triggers `HYBRID-ROUTE-REVIEW-001`, registration SHA `3ea1762520c61dccf8e272c63a168a895738175ecccd63e7593bffdb76a5e1df`, audit PASS9/9. Missing evidence remains fail-closed, not a terminal verdict.

Route review result SHA `ed533d0f22911b491b2873f2d75e587e17af6102e8cdf8228d210d448c3675f7` is PASS_ROUTE_REVIEW, trigger consecutive H1/H2 FAIL, route_exhausted=false. Frozen output permits H3 engineering prerequisites only and authorizes no behavior. Current re-ranking must wait for H4 terminal evidence and include terminal H3 adapters,H5 failure and H6 support.

## Path-1 and H3 prerequisite state

The original Path-1 is protocol-aborted, preserved and quarantined at161 board pairs. The legal-all-in successor continues CPU-only/BelowNormal as coordinator PID10192 with six workers in `data/cfr/pipeline_v3_hu_srp_200bb_legalallin_v2/`. Its lock SHA `ddc57ea13d9bd02cdc41f40832aa08b07b82b03267d1540b4745abb3b60174d4` freezes80K iterations,600 boards,seed20260712,samples-per-bucket1,no overwrite. Exact audit now proves30 gzip outputs,30 metadata files and the same30 QA PASS records,0 FAIL/missing and zero illegal post-all-in rows; boards are2,5,6,10,13,21,24,36,39,41,43,57,59,60,66,73,75,76,81,84,87,90,93,95,101,104,107,118,120,121. Immutable artifact SHA `a38ceac721b19d5fdb21d2c7f5a863d03ea1efdec191fc44813c4cca77c2f993`; unchanged workers continue123/127/131/132/136/137. Keep the job running and off GPU; do not restart or expand it during H7 arms.

The corrected assets are now classified `VALID_CORRECTED_CFR_DIAGNOSTIC_ASSET_NOT_TRAINING_ELIGIBLE_FOR_V55_DISTILLATION`:

- Adapter v2 is terminal FAIL_CLOSED. It assigned0.059 teacher mass to a nominal slot absent from the reconstructed v5.5 legal mask. Artifact SHA `2efe8fa27e0f43b81ac550c39d87dc4c9e6b77821eafc28b312330a0b7ae07c5`; preserved bundles may never be reclassified or ingested.
- State-gap audit SHA `225e29cd94126c8900a7a5b1d0eef0edad40e819731aadcbae2fab8827e9c699` proved deep source state differed from apply-replay state. Adapter v3 therefore froze exact Path-1 snapshots and closest actual-legal non-all-in mapping: lock SHA `fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e`, independent audit SHA `1cf7f0b389d3344ba9ff5823f5c078770ab33acd36712ee1247fc8c95ec0d1cd` PASS28/28.
- Adapter v3 is also terminal FAIL_CLOSED at its registered preflight. Source row39 `T|6|0|1c/x2|26-18` has teacher raise32.18, closest executable v5.5 non-all-in action21.8 and source pot14.53: normalized error0.7143840330 > frozen0.5. Terminal artifact SHA `c1c2aaa8f75ddf7d61aa097caf5f0d39fe6dfc58b157fdcf952b15fe6c48b715`. Formal double-run was not started because the training-ineligible preflight made PASS impossible.

No H3 behavior window was preregistered or launched. The dataset-selection draft is superseded blocked, the exact-quota finalizer was not triggered, no training dataset was materialized and no H3 smoke watcher remains live. Do not retry v2/v3, relax the gates, drop/renormalize mass or redirect sized actions to all-in.

If CFR/BC is selected again after H2, it requires a distinct exact-v5.5 teacher solver whose state transitions and actions are deployment-executable, with a new immutable asset design and validation chain. This prerequisite failure is not HYBRID route exhaustion; opponent-pool, critic/target and resolving families remain available.

## H4/H5 readiness

H4-POOL-MEAS-001 is terminal INCONCLUSIVE after the exact28-edge x2000-pair matrix. It authorizes no behavior or official hands and must not be extended.

The dormant H4 measurement harness was corrected before use for a syntax error and wrong seat-swap-helper import; focused tests6/6 pass. The dormant H5 subgame resolver was also corrected for an undefined `params` reference; both TypeScript package checks now pass. H5 readiness nevertheless remains `FAIL_CLOSED_H5_PREREQUISITES_INCOMPLETE`, artifact SHA `5512061eb5f3e2f15c282fc866339134a18c8c324a83b9e5f82e264392c07341`: only50/100bb SRP/3bet scenarios exist, with no full200bb HUNL legality, Slumbot integration, greedy-direct or latency proof. H5 behavior authority is zero.

H6 is terminal and H7 is the only active behavior window. Do not relaunch H6 or interpret H7 training health as strength.

## Next autonomous transitions

1. Preserve H1/H2/H4/H6 terminal verdicts and exact gate31400 source identity.
2. Preserve both frozen endpoint identities; never resume, replace or substitute them.
3. Allow only the running duplicate-safe fixed40k control mirror and its locked successor stages; do not launch a second evaluator.
4. Let the completion chain run treatment mirror,audit,mirror judgment and exact H7 terminal judgment with no extension,second seed or later checkpoint.
5. After terminal H7 verdict, update ledger/goal/handoff and execute the registered route transition. No official hands during H7.
6. Keep the existing Path-1 CPU-only BelowNormal diagnostic work running without restart, expansion or new workers during H7 arms.
