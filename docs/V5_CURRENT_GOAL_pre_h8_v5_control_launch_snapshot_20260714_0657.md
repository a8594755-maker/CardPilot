# V5 Current Goal

Checked: 2026-07-14T07:31:00+00:00

## Latest authoritative correction (2026-07-14)

- H7 remains terminal `FAIL / H7_FAIL_REGISTERED_GATE` with judgment SHA256
  `6d0e2ae773ca79c57606d5de6765e67ed2c12aba92be41611f44a2c6ba581304` and immutable
  audit SHA256 `89382ddb7fadd319cd77afb6cad106182735401b1e37034657c67e94466c5027`.
- The formal Route Review 004 result supersedes its prerequisite research-review status.
  Result SHA256 `126dfc461c822c4b2bb4e599ac3da276b6412a9dda210ba8912a8d97fc0a6859`
  is `PASS_ROUTE_REVIEW`, `route_exhausted=false`, and selects
  `H8_VALUE_HEAD_ONLY_CATCHUP_AFTER_KL_STOP`.
- H8 preregistration SHA256
  `ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713`
  is immutable `REGISTERED_NO_LAUNCH`. It freezes fresh same-start 20M control and
  treatment arms from the exact H7 treatment endpoint; both retain target-KL 0.03 and
  optimizer state, and the sole treatment variable is value-head-only catch-up after
  KL early stop. Launch remains blocked until implementation, independent audit,
  design lock, preflight, and canonical rearm all pass. H8 authorizes zero official hands.
- A read-only process check found no Python trainer, watcher, mirror, or Path-1 process.
  Do not infer completion. Revalidate Path-1 identity/progress before same-job no-overwrite
  resume, and do not launch H8 from preregistration alone.
- Latest official strength remains L0: 20,400 greedy-direct Slumbot hands,
  `-153.2999 bb/100`, 95% CI `[-187.6945,-118.9052]`.

The intermediate `PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` text immediately below
describes the prerequisite research review, not the later formal route result, and is
historical.

## Superseding operational update (2026-07-14)

- H7 is terminal `FAIL / H7_FAIL_REGISTERED_GATE`. The fixed40k mirror passed at
  treatment-minus-control `+123.9907 bb/100`, 95% CI `[+98.3343,+149.0737]`, but the
  registered endpoint value gates failed: normalized-MSE degradation was `12.2256%`
  with bootstrap95 upper `18.6237%`, and treatment KL p95 was `0.03062 > 0.03`.
  Judgment SHA256 `6d0e2ae773ca79c57606d5de6765e67ed2c12aba92be41611f44a2c6ba581304`;
  immutable audit SHA256 `89382ddb7fadd319cd77afb6cad106182735401b1e37034657c67e94466c5027`.
  Do not extend, add a seed, use a later endpoint, or reclassify H7.
- Route Review 004 is reporting-only terminal
  `PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` / `TIER2_FROZEN_ROUTE_PIVOT`, SHA256
  `e8df3c12876aaf1f38cd88a652bc1ca87f42ba4fab3f83235213f2a61a9efef9`.
  It authorizes no new behavior change, action-specific intervention, official hands,
  or strength claim. The DRIVE-TO-L5 objective remains active, but execution is waiting
  for the exact causal evidence named by that review; route exhaustion was not proven.
- A read-only live process check at `2026-07-14T07:26:03Z` found no Python trainer,
  watcher, mirror, or Path-1 process. This does not prove the Path-1 asset job completed.
  Its last immutable recovery artifact is
  `reports/v5_path1_reboot_interruption_recovery_20260714.json`, SHA256
  `ef948410dac4b18c0ff14a1e36d39a17868d22a55d5e21c6acb46912b66ec526`, which recorded
  a resume after reboot. Any further Path-1 continuation must first revalidate exact
  identity/progress and resume the same no-overwrite asset job.
- Latest official strength is unchanged at L0: 20,400 greedy-direct Slumbot hands,
  `-153.2999 bb/100`, 95% CI `[-187.6945,-118.9052]`. H7 used zero official hands.

The older H7-running paragraphs below are retained as a historical snapshot and do not
override this superseding update.

## Immutable objective

- Build a general strong 200bb HUNL agent. Official strength evidence remains greedy-direct Slumbot only.
- L5 requires 100k+ official hands, bb/100 > 0 and 95% CI lower > 0; L6 additionally targets about +11.1 bb/100.
- Ledger is append-only; fail-closed identity, complete evidence bundles and one behavior change per window remain mandatory.
- EXP-002 is retained. EXP-003 is terminal INCONCLUSIVE. EXP-004 priors remain 0.01/0.02. EXP005-C and EXP-W1 are terminal and must not reopen.
- The from-zero constraint was lifted by explicit user escalation. 2.7B is only a resource cap, never continuation authority.

## Standing V5 campaign authorization (2026-07-13)

- Campaign completion is terminally defined as either: (a) a frozen V5-lineage agent passes L5 on a complete official greedy-direct Slumbot bundle with 100k+ hands, bb/100 > 0 and 95% CI lower bound > 0; or (b) a registered route review concludes the HYBRID route family is exhausted and escalates that conclusion to the user. L6 near +11.1 bb/100 remains aspirational and never weakens L5.
- Chain H-windows autonomously. After each terminal verdict, update the goal/handoff and append the event, then register and execute the next eligible single-variable window without conversational approval. Default order is H2 -> H3 -> H4 -> H5; frozen causal evidence may re-rank or insert H6+ within the HYBRID family (critic/targets, CFR/BC distillation, opponent pools, play-time resolving and required engineering work).
- Every behavior window still requires its own immutable preregistration, exact source identity, one behavior variable, frozen sample/gates/abort/rollback, offline validation, design lock, fail-closed preflight, canonical watcher rearm and exact registered judgment. Standing authorization never turns a draft into launch authority or permits a forced verdict/post-hoc redesign.
- Launch official greedy-direct Slumbot measurements automatically when the milestone's frozen registration prerequisites pass. M1 after H3 and M3 after H5 are the default milestones; M1-M4 thresholds may be re-frozen only before launch in their registrations. M5 is the immutable L5 claim bar. Every official run requires the complete hand-level evidence bundle.
- After two consecutive terminal FAIL/no-progress windows, run the registered route review autonomously and continue with the best causally supported window inside the HYBRID family. Suspend only if the review concludes route-family exhaustion or continuing would require changing the objective, claim bar or official greedy-direct policy.
- Maintain Path-1 and successor H-window asset jobs detached, CPU/GPU isolated as registered, QA-gated, resume-safe and provenance-logged. Expansion beyond 600 boards is allowed only when frozen H3 evidence identifies coverage as the binding constraint.
- Report rather than ask after each window verdict, official milestone and route review. Escalation remains limited to objective/claim-bar/official-policy changes, HYBRID route exhaustion, V6 architecture redesign, spending money or secrets. Terminal EXP-003, EXP005-C, EXP-W1 and H1 stay closed; irreplaceable artifacts are never destroyed.
- Authority source: direct user instruction `V5 CAMPAIGN GOAL — DRIVE TO L5`, received 2026-07-13. Pre-authorization snapshots are preserved at `docs/V5_CURRENT_GOAL_pre_l5_campaign_authorization_snapshot_20260713.md` and the matching takeover-handoff snapshot files.

## Authoritative current state

### H1 — terminal FAIL

- Preregistration: reports/v5_hybrid_h1_preregistration_20260711.json, SHA256 bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab.
- Watcher-only design lock v3: reports/v5_hybrid_h1_design_lock_v3_20260712.json, SHA256 dd99f3ecb09ffeae589b14d69d9040ab5a640272add6c3408b730592f9bccadb.
- Corrected holdout reports/h1_cal_001_attempt2_20260712 is PASS_IMMUTABLE_HOLDOUT: 10,000 common-deal pairs, 20,000 hands, 48,533 decisions, OOD0, FORBIDDEN_HOLDOUT_ONLY. Failed attempt1 remains terminal and preserved.
- Control endpoint: iter32617 / 536,004,082 hands, frozen SHA256 f3bc22de78caa4cc10493fdf6d8c4b09a4c3f6ec67c2e20ceba276ff76bba6b8.
- Treatment endpoint: iter32617 / 535,996,488 hands, frozen SHA256 4c021cbf9f25aeefa81b29c823bd7ec0b94bd87668cc7a4e1320d3c662588274.
- Normalized MSE control0.0091851773 versus treatment0.0093871153. Relative reduction -2.1985%, bootstrap95 CI [-6.4167%, +1.7948%]: point and lower-bound gates FAIL.
- Throughput first60 ratio1.054011 PASS; full-window ratio0.826652 FAIL. Entropy medians control1.30920/treatment1.26550: floor and non-inferiority PASS.
- Registered verdict: FAIL. critic_v2 is REJECTED. Do not extend, add a seed, use a later endpoint or reclassify.
- Completion audit: reports/v5_hybrid_h1_completion_audit_v2_20260713.json, SHA256 d00c482b63817e251707a20947d44901754b90b3831e8e8c9584119278560f8b, overall PASS_COMPLETE_H1_TERMINAL_FAIL.
- Delayed canonical rearm is CENSUREd. Reconstructed first60 passed, so no mandatory abort was missed; the unchanged endpoint watcher later froze exact identity/provenance evidence. It does not weaken or change the FAIL verdict.

### H2 — terminal FAIL_PROTOCOL_ABORT

- Authoritative preregistration v2 SHA256 aaf8bf30db6e757e15c1b9ae1bdd0b5e3eed379ec1dadbd23b2d8a70b1f2fa2f; independent audit SHA256 a6288d721743519f6c5b6f0d659e7d9f7c0c0a175babdaab1e0c9003409673eb is PASS_IMMUTABLE_H2_PREREGISTRATION.
- Design lock SHA256 f4526c4175130857f34b2669a629f5a1c80410e15f32ba5975ccc7c580876c75; preflight PASS_READY_CONTROL_LAUNCH.
- H2-VAR-001 immutable PASS: variance reduction99.5887%, bootstrap95 lower99.5619%; mean-bias absolute point0.00008505 and CI upper0.00049158 effective-stack fractions. FORBIDDEN_HOLDOUT_ONLY.
- Power review fixed the internal mirror at40k pairs before registration: seed2026071403, lower>=-20 bb/100, no adaptive extension/second seed/later endpoint.
- Control v5_hybrid_h2_control_allinonly_same31400_20m_r1_20260713 is frozen PASS at iter32616 /535,989,948 hands (overshoot287), checkpoint SHA256 f35558536365006afee9b1311352d465144dfed715a1028362def333147d3d3b. Manifest is finished; exact health/protocol PASS and stderr empty. Its first60 baseline is frozen at2239.1866 effective h/s after excluding one warmup row.
- Registered treatment v5_hybrid_h2_treatment_showdownk200_same31400_20m_r1_20260713 was automatically terminated at iter31461 /516,993,062 hands by the immutable first60 throughput guard. Control effective h/s2239.186573 versus treatment1202.764735 gives ratio0.5371435994 < registered0.85.
- Terminal judgment SHA256 947f7f73ac9f1ace08581f42f223b855e46f20732bd7de69a3d2c175c7d5eae7 is `FAIL / H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`; independent audit SHA256 494bb3bcb045f552e504e2313c679e68b149a905c270b7243363c120d2815515 is PASS_IMMUTABLE_H2_PROTOCOL_ABORT_JUDGMENT. Completion audit SHA256 0374827b98a94cd580eadf2437d3882d9ccdf21b1e40e236212046575ebd972a is PASS_COMPLETE_H2_TERMINAL_FAIL_PROTOCOL_ABORT. Treatment is rejected; exact gate31400 critic_v1 contract remains the route source.
- Endpoint MSE,treatment endpoint/treatment mirror,full-window throughput and terminal entropy gates were correctly not run after protocol abort. The partial control mirror was stopped at7896 rows, SHA256 f5706ca2f724d7f01614930cb5bffbf6c3b6ebc782875eb9f736ec5a85fabf60, and is POST_PROTOCOL_ABORT_EXPLORATORY_ONLY_NOT_JUDGMENT_EVIDENCE.
- A reporting-only launch-status race was CENSUREd and corrected: canonical rearm had stopped its invoking launch-watcher ancestor after the trainer and replacement watchers were already healthy. Correction artifact SHA256 2dd2e425bb6085b2499131b7839548b6459887a6411be18de52bf905c0a7ddf8; rearm source SHA256 e71aa3b10e12e2869afa87745ca555875542d4080ae035a4b0c996ce107c335f, parse PASS and tests16/16 PASS. Duplicate-safe status is now PASS without a relaunch.
- A second reporting-only CENSURE records that the original completion supervisor omitted the registered protocol-abort short circuit and therefore stopped fail-closed after the correct trainer abort. The corrected terminal artifact path binds the frozen locks,status and metrics; it does not change or force the preregistered FAIL.
- H2-MIRROR-001 is frozen before endpoints: fixed40k manifest SHA256 5c6d45e829d7ff103ad7515bee69a1ae1a6593dea8b59d43196091bc07b18c6e, runtime-enforced measurement-lock v2 SHA256 800c0b75e70ab5dedb54c853956d27333598f1e9ddcf6fa85162ad59e0921618 and audit PASS. It requires CPU-only BelowNormal threads1/inter-op1 and forbids GPU. Terminal judgment-lock v3 SHA256 f776d11bb01ed44a8d386ba31cce335be66b742f83e8c6a6de07451ca3003d9a and audit SHA256 0c0e2b9d7dba0618e009fac081558cf760f9a91f5af05872d41cd40e1f65afb6 PASS10/10 bind the holdout, H2-VAR, mirror, seeds and gates. v3 also correctly requires route review after a valid fixed-sample FAIL or INCONCLUSIVE; fail-closed missing evidence is not terminal. Preserved v1/v2 locks are superseded before any endpoint result.
- One variable only: exact-or-K200 all-showdown critic returns. Actor reward/GAE/policy, architecture, deal stream, opponent assignment, priors0.01/0.02 and EXP-002 are unchanged. H2 authorizes zero official hands.
- Terminal H2 FAIL/no-progress after H1 triggers immutable HYBRID-ROUTE-REVIEW-001, registration SHA256 3ea1762520c61dccf8e272c63a168a895738175ecccd63e7593bffdb76a5e1df and audit SHA256 d24618ded58b5bd1ebd507ec1fe2ca8dc37dba6b86c79d630888e5bfae0a35c0 PASS9/9. Missing evidence does not trigger; H2 PASS re-ranks directly because current H3 distillation is terminally blocked. The adapter failures permit engineering diagnosis only and are not route exhaustion.
- HYBRID-ROUTE-REVIEW-001 result SHA256 ed533d0f22911b491b2873f2d75e587e17af6102e8cdf8228d210d448c3675f7 is PASS_ROUTE_REVIEW, triggered by consecutive H1/H2 FAIL, route_exhausted=false. Its frozen selection is H3_ENGINEERING_PREREQUISITES_ONLY_NO_BEHAVIOR_LAUNCH; it authorizes no H3 behavior or official hands. A current evidence re-ranking must wait for terminal H4 and include terminal H3 adapters,H5 readiness and H6 support.

### H3 Path-1 asset preparation

- Original Path-1 is terminally protocol-aborted and preserved read-only at161 complete board pairs. Audit v3 SHA256 db2fef9c70b44d3f7b0af437c9e68b5615451326e59dac393a1e1b9ab79096d5 found illegal post-all-in action branches; old/current policies are quarantined from H3 and must never be ingested.
- Legal-all-in successor asset job PID10192 with six BelowNormal CPU workers is RUNNING in data/cfr/pipeline_v3_hu_srp_200bb_legalallin_v2/. Lock SHA256 ddc57ea13d9bd02cdc41f40832aa08b07b82b03267d1540b4745abb3b60174d4 freezes pipeline_srp_v3_200bb,80K iterations,600 boards,selection seed20260712,samples-per-bucket1 and no overwrite.
- Per-board QA requires convergence and zero illegal post-all-in extra-action rows. Thirty successor boards are complete and QA-PASS: 2,5,6,10,13,21,24,36,39,41,43,57,59,60,66,73,75,76,81,84,87,90,93,95,101,104,107,118,120,121. Exact set audit found30 gzip outputs,30 metadata files,30 QA PASS,0 FAIL and0 missing; all report zero illegal post-all-in rows. The same six workers continue boards123,127,131,132,136,137; no restart, expansion or new worker occurred. Immutable progress artifact SHA256 a38ceac721b19d5fdb21d2c7f5a863d03ea1efdec191fc44813c4cca77c2f993. The job remains CPU-only/BelowNormal and does not touch the GPU.
- H3 bridge Phase0 action mapping remains PASS, while Phase1 already established that the actual v5.5 preflop tree has zero paths to Path-1's exact pot5/stacks197.5 SRP entry. The corrected solver assets can still serve as CFR diagnostics, but training eligibility required a frozen domain adapter and was tested rather than assumed.
- H3-DOMAIN-ADAPTER-001-V2 is terminal FAIL_CLOSED and may never be reclassified. Its first corrected-board smoke mapped 0.059 probability mass to a nominal v5.5 slot that was not legal in the reconstructed state. Preserved terminal artifact SHA256 2efe8fa27e0f43b81ac550c39d87dc4c9e6b77821eafc28b312330a0b7ae07c5. The original and child-environment failure bundles are preserved; both implementation defects were CENSUREd and corrected before the terminal v2 judgment.
- A read-only state-gap audit then proved that deep Path-1 replay state and the former Python apply-replay diverged. H3-DOMAIN-ADAPTER-001-V3-SNAPSHOT therefore froze exact Path-1 state snapshots and closest actual-legal non-all-in projection before use: design lock SHA256 fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e; independent audit SHA256 1cf7f0b389d3344ba9ff5823f5c078770ab33acd36712ee1247fc8c95ec0d1cd PASS28/28.
- V3 is also terminal FAIL_CLOSED at its immutable preflight gate. On source row39 `T|6|0|1c/x2|26-18`, teacher raise amount32.18 mapped closest to executable amount21.8 at pot14.53, giving normalized error0.7143840330 > the frozen0.5 maximum. Including all-in does not help. Passing would require relaxing a frozen gate, dropping/renormalizing teacher mass, or changing source action/state semantics; none is allowed under v3. Terminal artifact SHA256 c1c2aaa8f75ddf7d61aa097caf5f0d39fe6dfc58b157fdcf952b15fe6c48b715. The formal double-run was correctly not started because the training-ineligible preflight already made PASS impossible.
- The current Path-1 asset classification is `VALID_CORRECTED_CFR_DIAGNOSTIC_ASSET_NOT_TRAINING_ELIGIBLE_FOR_V55_DISTILLATION`. No H3 behavior window was registered or launched. The bounded dataset-selection draft is `SUPERSEDED_BLOCKED`; its exact-quota finalizer was not triggered, no dataset was materialized, and no live H3 smoke watcher remains.
- A future CFR/BC window would first need a distinct exact-v5.5 teacher-solver asset design whose transitions and executable actions match deployment. It must be separately frozen, validated, QA-gated and preregistered before any behavior use. The adapter failures are not evidence that the entire HYBRID route family is exhausted; critic/targets, opponent pools and resolving families remain available for evidence-based re-ranking.

### H4 opponent-pool readiness measurement — terminal INCONCLUSIVE

- The previously dormant pool-selection reporting harness was fail-closed before use: it had an unmatched parenthesis and imported the common-deal seat-swap helper from the wrong module. Both defects were corrected before any design/result existed; harness SHA256 4ce15ee1dcba5db6796eba763be0b2491ed9fc279466aaf1412e5fe0a4864d3a and focused design/harness tests6/6 PASS.
- H4-POOL-MEAS-001 is an immutable reporting-only registration, not a behavior window. Design SHA256 90edba2dbd3dd43700ad590f05120ea22a0b6b339a3461e2de1607e769941067; independent audit SHA256 262f28f1cd67aa71b209ea3b3c108efa47440efbf11f4606aefef393d829d481 PASS_IMMUTABLE_H4_POOL_MEASUREMENT_DESIGN.
- The payoff-blind panel contains the five exact gate31400 active snapshots103,109,115,120,129 and the three lowest-loss reconstructable candidate-history exclusions17,81,63. It freezes a complete8-player/28-edge matrix,2000 common-deal seat-swapped pairs per edge,seed2026071501,greedy v55/9slot/200bb,10 bb/100 inversion margin,Holm familywise alpha0.05,no adaptive extension,48h ceiling and max OOD0.01.
- The fixed matrix completed exactly56,000 rows /28 edges x2000 pairs. Pairs SHA256 697cf90aa388c258b5b376f9851b58db04b6fcd6e51c9f0e78f26f63513ed990; result SHA256 de60e08500d282f6a554dfda1d2bcb98667e035a8c078cb22900f946d3e40cb9; audit SHA256 c264268a1a8374a8ec3fe8cdfd6d3f3f11451f34e5f82339e287e17139349e7 PASS, OOD0.
- Terminal verdict is `INCONCLUSIVE / NO_CANDIDATE_NO_LAUNCH`. Only excluded81 versus active103 met the inversion test; the registered rule required one excluded versus at least two actives or at least two excluded identities. No adaptive extension, H4 behavior or official hands are authorized.

### H5 resolver readiness

- Pre-use typecheck exposed an undefined `params.vnetModel/params.vnetWeight` reference in the dormant subgame resolver. It now destructures and forwards the declared request fields; corrected source SHA256 b0e4e126f91040036b0825a25317592d4b30985b3335b277048791a9fb2c844d and both bot-client/cfr-solver typechecks PASS.
- Readiness artifact SHA256 5512061eb5f3e2f15c282fc866339134a18c8c324a83b9e5f82e264392c07341 is `FAIL_CLOSED_H5_PREREQUISITES_INCOMPLETE`. Existing realtime scenarios cover only50/100bb SRP/3bet and lack exact200bb realtime configuration, complete HUNL spot coverage, v55/9slot legality proof, Slumbot integration, deterministic greedy-direct proof and a registered latency bundle.
- H5 remains an engineering candidate only. No H5 behavior preregistration/launch or official-hand authority exists.

### H6 PPO KL early-stop window — terminal FAIL_PROTOCOL_ABORT

- H6 treatment was automatically terminated after61 accepted rows at iter31461 /516,992,852 hands. Frozen first60 effective throughput was control2239.186573 h/s versus treatment1147.971883 h/s, ratio0.5126736187 < registered0.85.
- Terminal judgment SHA256 25950437f46dbda6ec7c07d61db61c9c5630061868769d6723116cd2a2677053 is `FAIL / H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`; independent audit SHA256 0adcc3326b3934072a31757ba8319839afa7a2346db4c7f3350ce9263518d867 is PASS_IMMUTABLE_H6_PROTOCOL_ABORT. H6 is permanently terminal and cannot be reclassified.
- Endpoint MSE, full-window throughput and terminal mirror judgment were correctly not run. The partial control mirror stopped at6738 rows, SHA256 9cec4bf18e79c688e0b8e2c5315db576365a4da8cbeacc5cccea6f080d019c73, and is POST_PROTOCOL_ABORT_EXPLORATORY_ONLY_NOT_JUDGMENT_EVIDENCE.
- The treatment alone had a concurrent CPU mirror, unlike the historical H2 control. This is associational resource asymmetry only: it cannot change H6's verdict, but justified a prospective fresh A/B with deferred evaluation.

### Route Review 003 and H7 fresh contemporaneous A/B — POST-ENDPOINT CONTROL MIRROR RUNNING

- Route Review 003 preregistration SHA256 e1e1dad8c44233527fbd2ebb65725748378b3d93bf6a482e848de393b6c68908 and result SHA256 cdf17d3cdaba749cc881e7c48fd37a9a6dbcf3b3aac82cee46473415678d9f99 are PASS_ROUTE_REVIEW, route_exhausted=false. The frozen selection is `H7_FRESH_CONTEMPORANEOUS_AB_WITH_EVALUATIONS_DEFERRED`.
- H7 preregistration SHA256 45b57f4fe817f1b98e7267a8e482d46b8121fb41d4e432a8af25a1857c6cb4b7 and audit SHA256 ed0fa3105c95ed69fb56332d2d06553ebeb971793e8272ffdcdfc038fcfb5dc4 PASS11/11. Fresh control then fresh treatment each run20M hands from exact gate31400. Sole variable is PPO completed-epoch mean KL early-stop threshold0 ->0.03.
- Design lock SHA256 88aea213e00614191b79496079ea8607aca67a0a7d9c582f47a93af011f325af; audit SHA256 bd9eb98b76d65c25a02a20cfb2d23e8d283cb1c27d1d6564efaca91085937869 PASS_IMMUTABLE_H7_DESIGN_LOCK; preflight SHA256 6d9018bec60e0aefdf2dc31b745dd734242cedba056f3bea532a06e51721283c PASS_READY_H7_CONTROL_LAUNCH. Direct tools and transitive judgment parsers are frozen.
- Control `v5_hybrid_h7_control_kl0_same31400_20m_r1_20260713` is frozen PASS at iter32617 /536,005,488 hands, overshoot15,827 within50k; endpoint checkpoint SHA256 468f7a854e59387f2dda3bef7287a934a31d0ef75a5ec402db18bce02290d71b. Manifest finished, protocol guards PASS, entropy20 abort false, isolation violations0 and stderr empty. Fresh first60 is frozen PASS at1085.698240 effective h/s using rows2-61 after excluding warmup row1; this is the only H7 treatment throughput baseline.
- Exact treatment `v5_hybrid_h7_treatment_kles003_same31400_20m_r1_20260713` is frozen PASS at iter32617 /536,001,286 hands, overshoot11,625 within50k; endpoint checkpoint SHA256 948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149. Manifest finished, trainer exited, health/protocol guards PASS, stderr0, entropy20 abort false and isolation violations0. Registered first60 remains frozen PASS at rows2-61: control1085.698240 versus treatment1078.677831 effective h/s, ratio0.993533739 >=0.85.
- Reporting-only live control-plane audit SHA256 792f9a460ec093f88fd5cb62e3c6121b18e988f6e4f9f581b4392a091bd78537 is PASS18/18: exact first60 recomputation, both final launcher hashes/lock bindings, control+treatment endpoint/protocol validate-only contracts, completion validate-only, resource isolation, dormant mirror and official-hands0 all pass. It changed no locked tool or process.
- A reporting-only dashboard crash was CENSUREd and corrected after `checkpoint.config.total_hands=null` reached a legacy numeric formatter. The stale dashboard did not affect trainer or H7 control watchers. Optional target counts now fail closed as `unknown`; focused tests3/3, py_compile and live claim-audit execution pass. Canonical rearm survival PASS restored all eight permitted watchers with dashboard stderr empty. Correction artifact: `reports/v5_h7_dashboard_reporting_correction_20260713.json`.
- Control freeze and exact treatment launch artifact SHA256 c81b53dcb2a6e1c80efa12f6f98cc5e0d53e7e59025a5c03768ca81e0ba53564. A control-side status race was CENSUREd: canonical rearm ended the invoking watcher ancestor after treatment and replacement watchers were healthy. Duplicate-safe reconciliation wrote `TREATMENT_ALREADY_LAUNCHED` without invoking a second launcher; training and gates were unchanged.
- Treatment first60 immutable artifact SHA256 81e58381ee8f295a3670d6901b01c83d56df1151729ce7ce963845b88137ad3e. This passes only the early abort gate; it is not an H7 method verdict or strength claim.
- Both endpoints are frozen PASS and no trainer remains. Completion watcher launched the registered fixed40k control mirror as PID20552, CPU-only/BelowNormal,torch threads1/inter-op1, bound to manifest SHA256 57d43cb5ca58690d6f532c565badb0ff831d1d26cf1e94de9385c5cbc4028028 and measurement-lock SHA256 8d5b9ab7c6011a2fdd17b013379c8ae3c5c3c904aa61e271cc0166f872562c75. Transition artifact SHA256 593783824e2fb1ab7d4bdd33025ef39091375dbbc7040f4e1fa65ee1e3b09670. Chain order is control mirror -> treatment mirror -> audit -> mirror judgment -> H7 terminal judgment; no duplicate evaluation or official hands.
- Resource isolation is immutable: no endpoint holdout, H7 mirror, diagnostic or official Slumbot evaluation while either trainer is active. H7-MIRROR-001 is frozen40k pairs, manifest SHA256 57d43cb5ca58690d6f532c565badb0ff831d1d26cf1e94de9385c5cbc4028028 and measurement lock SHA256 8d5b9ab7c6011a2fdd17b013379c8ae3c5c3c904aa61e271cc0166f872562c75; it starts only after both endpoints freeze PASS and no trainer remains.
- Path-1 PID10192 remains the pre-existing BelowNormal CPU diagnostic job. It was not touched, restarted or expanded; all30 completed outputs are formally QA-PASS with zero missing/illegal rows, and workers continue123/127/131/132/136/137. No official hands are authorized in H7.

## Immediate next direction

1. Preserve H1/H2/H4/H6 as terminal and never resume, extend or reclassify them. Exact gate31400 critic_v1 remains the H7 source.
2. Preserve both frozen H7 endpoints and their exact identities; never resume, replace or substitute either checkpoint.
3. Allow only the duplicate-safe registered completion chain now running the fixed40k control mirror. Do not launch a second mirror or any official evaluation.
4. After control+treatment mirror, immutable audit and mirror judgment complete, let the locked H7 judge evaluate endpoint MSE,KL stability,first60/full throughput,entropy and identity exactly as registered. No extension, second seed or later endpoint.
5. After terminal H7 PASS/FAIL/INCONCLUSIVE, append the verdict, refresh goal/handoff and execute the registered autonomous route transition. No official hands are authorized during H7.
6. Keep the legal-all-in Path-1 successor running as the existing CPU-only BelowNormal diagnostic job. Do not restart, expand or add workers during H7 arms; do not ingest it into v5.5 without a new exact-v5.5 teacher design.

## Official strength

Latest official strength remains L0: 20,400 greedy-direct hands, -153.2999 bb/100, 95% CI [-187.6945, -118.9052]. H1/H2/H3/H4/H5/H6/H7 grant no V4/L5/L6 claim.
