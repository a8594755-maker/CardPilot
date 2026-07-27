# V5 Current Goal

Checked: 2026-07-16T19:46:00+00:00

## Authoritative operational update: H12 locked and ready for exact control launch

- Prelaunch control-plane corrections are terminally resolved before any trainer.
  Preregistration v3 SHA
  `7ecd7a4342f75a92f4d4f12493bcd5fda9e3e92e7f43f023f8779becbdb48e57`
  supersedes v1/v2 with identical source,arms,scientific variable,gates and
  interpretation;independent audit SHA
  `8d4f6239e94a80d92da2441deef39d1d59612dd1b5e951bba018592e7d207850`
  PASS42/42. No arm launched under the predecessors.
- Implementation audit v4 SHA
  `f52f95e7c28d2958380eb24cb69a16c455a4b3b6a8e60a4523c621a652494ca6`
  PASS21/21 and focused/regression suite44/44 PASS. Exact health status now carries
  design-lock identity;ordered rearm stages are explicit and ValidateOnly PASS for
  both arms.
- Immutable design-lock v2 SHA
  `a5318450b699bb2c9b0d6385fc386829155409db68029f47da0121e5ef766c39`
  and audit SHA
  `e44c47e008cfb4ccb85d0e0222b77e0f8cdefed4a557fe8e99d1f641f114ebf3`
  PASS. It supersedes the preserved v1 lock before launch. Live preflight SHA
  `1da5bed02e1cde812041160fc7276d597f6eb12406f8d363b6f83d04d654d807`
  is `PASS_READY_H12_CONTROL_LAUNCH`;exact source/optimizer,all hashes,absent run
  dirs,no trainer/evaluator,terminal prior sentinel and Path-1 PID37656/six
  BelowNormal workers pass. Control launcher ValidateOnly is ready.
- Next transition is the exact locked control launcher. It must first create and audit
  production control PERF-CAL10/40/3 with loss ratio>=0.95,then activate the sentinel,
  launch the fixed20M MSE control and pass canonical ordered rearm survival. Once the
  trainer is active,no parent/delegated observer command is permitted. Official hands0.

The H12-registered section immediately below is historical.

## Authoritative operational update: H12 registered no-launch

- DRIVE-TO-L5 v2 remains active and the immutable L5 claim bar is unchanged. H12
  preregistration SHA
  `a5939812215e42e924566f1eef20d869bbc8a0d64a8960aa25242e7917e1656c`
  and independent audit SHA
  `c394666b9c0508d39d759fbe507b879b34d3c39d8b607a320485a95bb7384971`
  PASS40/40. Status is exactly `REGISTERED_NO_LAUNCH`; launch authority remains NONE.
- H12 freezes fresh same-start fixed20M control then treatment from exact clean H11
  control iter35051 /576,021,901,checkpoint SHA
  `96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13`.
  The sole behavior variable is catch-up value loss MSE versus SmoothL1 beta1.0;
  standard PPO MSE,optimizer,target-KL0.03,seeds,priors and every H11 scientific gate
  remain unchanged. H11 treatment and all H9/H10 partials are forbidden.
- Reporting-only PERF-CAL implementation smoke SHA
  `245c2ac84f0570252571d36c753a9d5822ec85dc53f980283013277b1b66525a`
  and authoritative audit-v2 SHA
  `9a7d85c0e9d1e6c20bcf71679cac27588c5ef22700dada91139e1d75d17c2fb7`
  PASS19/19;measured SmoothL1/MSE throughput ratio1.079284>=0.95. This is readiness
  evidence only. Exact production PERF-CAL with seed2026071601,batch1024,warmup10,
  timed40,repeats3 must pass before each arm;the treatment common-MSE baseline must
  also match the control at>=0.95. Failure means no arm launch.
- Canonical rearm now contains the exact H12 health producer and dependency-ordered
  supervisor:health/protocol -> endpoint -> downstream. Their preregistered hashes and
  focused/regression tests31/31 PASS are frozen, but H12 child lifecycle implementation,
  independent audit,design lock,live preflight,exact control PERF-CAL and canonical
  rearm must still PASS before control launch. No trainer/evaluator/mirror/Slumbot is
  authorized now;official hands0. Path-1 PID37656/six BelowNormal CPU workers remains
  untouched. CAL-EXT-002 remains mandatory after H12 before H13 unless an exact H12
  PASS quick5k already satisfies it.

The H11-terminal/Route-Review008 section immediately below is historical context.

## Authoritative operational update: H11 terminal FAIL; Route Review008 selects gated H12

- DRIVE-TO-L5 v2 remains the active goal and the immutable L5 claim bar is unchanged.
  H11 is permanently terminal `FAIL / H11_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`.
  Judgment SHA `88f86867183a36abbf34fedc6eb7556b2fd81e33c1fd47f79e44031ae41fa316`
  binds treatment first60 1366.486603 h/s versus control1971.341469,ratio
  0.6931760047<0.85. The watcher terminated treatment at iter33895 /557,014,309;
  no treatment endpoint,mirror or official hands exist. Independent terminal audit
  SHA `fb6217793ea703eb7521dcc6b7d9bdf2d4980c5895c578867e5208aa117c0122`
  is `PASS_COMPLETE_H11_TERMINAL_FAIL_PROTOCOL_ABORT` 30/30. H11 may never resume,
  extend,reclassify or use its treatment partial.
- Reporting-only throughput diagnosis SHA
  `8e92b23f9d2984b1cbc2f83bf797f1a5962476e558064ebcda2c3b4d5261c6bd`
  preserves the protocol FAIL but finds no causal SmoothL1 method conclusion:the
  paired ratio is approximately0.69 even on rows with zero catch-up epochs,while an
  isolated loss forward/backward microbenchmark measured MSE/SmoothL1 time ratio
  0.974. H11 therefore supplies no method-effect estimate.
- Route Review008 preregistration SHA
  `1208b8cde66207871a03b3a23acf8cec6efb44caf786e15565c48f58d5fa147e`,
  result SHA `f118c73e4721a2c06731798aaf63fc4762dd63d513c97fa5fa6674f959a1bffe`
  and audit SHA `042f5247367e17e5656d6be4334cf12d47ea7a907233d076765a80088935832e`
  PASS47/47. It sets `route_exhausted=false` and selects
  `H12_RESOURCE_MATCHED_ROBUST_VALUE_HEAD_CATCHUP_AFTER_PERF_CAL_AND_CONTROL_PLANE_REPAIR`
  from exact clean H11 control iter35051 /576,021,901,checkpoint SHA
  `96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13`.
- H12 launch authority is NONE. Before H12 registration/launch,a separately audited
  PERF-CAL must pass isolated SmoothL1/MSE and between-arm common-baseline ratios
  >=0.95;canonical strict rearm must add the exact endpoint health producer and order
  health/protocol -> endpoint -> downstream watchers. H12 then retains fresh same-start
  fixed20M arms,the same single loss variable,and all H11 gates including first60>=0.85.
- External debt is20,010,816 hands relative to CAL-EXT-001 H8 and is not yet due at
  the25M target. After H12 terminal,CAL-EXT-002 is mandatory before H13;an H12 PASS
  exact-treatment quick5k may satisfy it. Latest official strength remains L0:
  5,000 greedy-direct hands,-207.1804 bb/100,CI[-297.6644,-116.6964]. Path-1 remains
  coordinator37656 with six BelowNormal CPU workers,diagnostic-only and untouched.

The H11-control-recovery section immediately below is historical.

## Authoritative operational update: H11 control complete; endpoint-health deadlock recovered

- DRIVE-TO-L5 v2 and the immutable L5 claim bar are unchanged. H11 control
  `v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715` finished at
  iter35051 /576,021,901 hands,10,816 overshoot within the registered50,000 limit,
  stderr0. Protocol is `ARM_FINISHED_GUARDS_PASS`,resource-isolation violations0,
  assignment provenance PASS1217 rows,and first60 is frozen at1971.341469 effective
  h/s. No official hands were run.
- The original locked endpoint watcher terminally timed out only because it required
  exact `health_status.json` while strict H11 rearm simultaneously blocked the generic
  health producer. Treatment was never launched and the stale completion/launch
  supervisors stopped fail-closed. The original timeout and all downstream blocked
  statuses are preserved read-only.
- Reporting-only recovery SHA
  `58f169f8a620e588f86e55ad35c6090c2ef31390f841d6babf2d5af5084c4c32`
  rebuilt a compatibility log view by removing only the `vhcatch=<integer>` reporting
  token,ran the design-lock-pinned V5 monitor,and published exact endpoint health
  PASS14/14 at iter35051 /576,021,901. It changed no checkpoint,behavior,gate or
  verdict. Independent audit PASS29/29 SHA
  `cfb3a8a204e788ec03b3a69910a1a0ef625ebcd9ee685eee4618badd46daf4dd`.
- The correction is CENSUREd append-only. Next is canonical H11 rearm on the completed
  control. The unchanged locked endpoint watcher must independently freeze PASS before
  the exact treatment launcher may run. Once treatment starts,the zero-observer active-
  arm contract resumes;mirror/evaluator/Slumbot remain forbidden and official hands0.

The H11-ready-for-control-launch section immediately below is historical.

## Authoritative operational update: H11 locked and ready for exact control launch

- H11 implementation audit v2 SHA
  `659ef9b5bdc209a0c923106e958f1537fbc1810876ffc1bd142cb73511987793`
  PASS18/18;the combined focused suite is15/15 PASS. Scientific behavior remains the
  registered MSE-versus-SmoothL1 beta1 catch-up-only comparison;full trigger provenance,
  either-arm terminalization and zero-observer active-arm handling are control-plane only.
- Immutable design lock SHA
  `d6c5019439ff6ee1543dc6a9a61b7214f4d0a283b2847096ed6074c2366616d8`
  and independent audit are PASS. H11 binds canonical H8 source only,fresh fixed20M
  arms,unchanged gates,immutable40k mirror stream,and forbids H9/H10 partials.
- Live preflight is `PASS_READY_H11_CONTROL_LAUNCH`:source/optimizer identity,all
  frozen files/tools,no trainer/evaluator,terminal prior sentinel,absent run dirs and
  Path-1 coordinator37656/six BelowNormal workers all pass. Canonical rearm ValidateOnly
  blocks every generic/Slumbot path;exact control launcher ValidateOnly is ready.
- Next exact transition is the locked control launcher. It must activate the H11
  sentinel before trainer start and pass post-start canonical rearm survival. Once the
  arm is active,no parent/delegated shell,file-read,hash,process-list or other observer
  command may run;only locked H11 lifecycle and unchanged Path-1 may remain. Official
  hands are0.

The H11-registered section below is now historical.

## Authoritative operational update: Route Review007 PASS; H11 registered no-launch

- Route Review007 result SHA
  `e53d7e72a53317ce88501d12c877f96d4c1dc2ec7edcd497c786ef7524403c93`
  and independent audit SHA
  `e24338f58f8eb434aefa406f81fcc3aed5146226c35d4fb9de5bc876b2165ff9`
  PASS36/36. It finds H9/H10 supplied zero SmoothL1 method evidence,selects a new
  clean H11 only after a control-plane gate,and sets `route_exhausted=false`.
- H11 preregistration SHA
  `d493b1f9e936d89f0c2e51a0b6c5dbc5a8dd20b312d5f9cd5e415f43f44528d0`
  and audit SHA
  `7f1aa18b396facd3a8148f6ce1e87f01653b1532959de0733cb9c27087e07852`
  PASS25/25. It retains the exact H10 science:canonical H8 same-start source,
  fixed20M control then treatment,MSE versus SmoothL1 beta1.0 only,and every
  registered quality/statistical gate unchanged. H9/H10 partial checkpoints and H10
  first60 baseline reuse are forbidden;official hands remain0.
- H11 adds no behavior variable. Its mandatory prelaunch control-plane gate preserves
  PID,parent,creation time,executable,full command line and command-line SHA;supports
  terminalization from a control or treatment abort;and forbids every parent/delegated
  observer command while either trainer is active. Only exact locked H11 lifecycle and
  the unchanged Path-1 job may exist.
- Status is `REGISTERED_NO_LAUNCH`. Next is H11 implementation/offline audit,then a
  separate immutable design lock,live preflight and canonical rearm. No trainer,
  evaluator,mirror or Slumbot process may launch before every gate passes.

The H10-terminal section immediately below remains authoritative history but its
Route-Review007-next instruction has now been completed.

## Authoritative operational update: H10 terminal INCONCLUSIVE; Route Review007 next

- DRIVE-TO-L5 v2 remains active and the immutable L5 bar is unchanged. H10 is
  permanently terminal `INCONCLUSIVE / H10_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`.
  Locked judgment SHA
  `c29671f5e5fce292d0fdadc4a351c2c089137f2d018f614b7564657dd3178897`
  and incident artifact SHA
  `5c40cb7b692d71f8211bacf05aba4cc1571f8e0bd4ab34d140a40a421e5adb57`
  are authoritative. Control stopped at iter33912 /557,293,500,18,717,585 hands
  before its fixed endpoint;treatment never launched and official hands are0.
- Control first60 had frozen `PASS_CONTROL_BASELINE_FROZEN` at1779.760034 effective
  h/s,but this is throughput-only and supplies no method/model/strength evidence.
  PID7848 was reported only as `unregistered_cardpilot_project_process`;its command
  line,parent and creation identity were not preserved and it exited before capture.
  The frozen protocol matcher is overbroad enough to catch goal-v2-permitted read-only
  CardPilot PowerShell observers. Resource contention is therefore not proven,but the
  H10 verdict cannot change because the registered watcher terminated the trainer.
- H10 may not resume,extend,launch treatment,freeze a later endpoint,run mirror or be
  externally evaluated. The active-window sentinel is terminal INCONCLUSIVE after a
  reporting-only recovery from the completion watcher's control-abort transition bug.
  No trainer,evaluator,mirror or Slumbot process is active;Path-1 remains unchanged.
- Next required transition is a separately registered Route Review007. Before any new
  arm,the review/control plane must preserve full trigger provenance and distinguish
  explicitly permitted file-read/hash/process-list observers without weakening exact
  evaluator,Slumbot or project-execution isolation. No behavior launch is authorized.

The H10-control-active section immediately below is historical and must not be used.

## Authoritative operational update: H10 control active

- Fresh control `v5_hybrid_h10_control_catchmse_same33834_20m_r1_20260715`
  launched from the exact canonical H8 source under design-lock SHA
  `a0f959f882846eb0d1454aaa9627366f7eaa8b123baa3e1febdbae2145221905`.
  Trainer PID `46712` is running;latest observed manifest iter33843 /556,158,901,
  fixed endpoint576,011,085. Optimizer is preserved,catch-up loss is MSE,target-KL
  is0.03,and official hands are0.
- Active-window sentinel is `H10_CONTROL_ACTIVE`. Canonical rearm survival PASS
  armed exact endpoint PID48728,protocol PID46248,treatment-launch PID49060 and
  completion PID29100. Protocol is `ARM_RUNNING_GUARDS_PASS`,resource-isolation
  violations0,first60 pending,and launch stderr is empty. Every generic,Slumbot,
  mirror and calibration path is blocked.
- Do not run any non-H10 project process while the sentinel is active. The registered
  chain is autonomous:control first60→fixed endpoint freeze→exact treatment launch;
  evaluation begins only after both endpoints freeze PASS and no trainer remains.

The locked/ready section immediately below is now historical.

## Authoritative operational update: post-CAL H10 locked and ready for control launch

- DRIVE-TO-L5 v2 and the exact L5 claim bar are unchanged. H10 implementation audit v2
  SHA `581f3879c52451e38c86d610349395fda61544d670788b0cf158424d43b02da8`
  PASSes all14 checks;the focused suite is24/24 PASS. MSE control is bitwise
  legacy-equivalent and SmoothL1 beta1.0 changes only value-head catch-up effects.
- H10 immutable design lock SHA
  `a0f959f882846eb0d1454aaa9627366f7eaa8b123baa3e1febdbae2145221905`
  and audit SHA
  `1a78ea584e4775d1333320d8718568dfe0972969b99be3c7f0a9ab989078b68a`
  PASS. It binds the canonical H8 endpoint only,fresh fixed20M control then treatment,
  exact registered gates,the immutable40k mirror stream and strict active-window
  process isolation. H9 partial and CAL benchmark-copy paths remain forbidden.
- Live preflight SHA
  `4443e900a3c9c7624804df1539dfec9130c949e3fba4498c40ac1432e1719b5c`
  is `PASS_READY_H10_CONTROL_LAUNCH`. Canonical rearm ValidateOnly classifies H10,
  blocks every generic/Slumbot path,and the exact control launcher is ready. A prior
  transient preflight saw five solver workers plus a Path-1 QA child and failed closed;
  its read-only bundle is preserved. The coordinator naturally returned to six workers;
  Path-1 was not touched.
- Next exact transition is the H10 control launcher. It must atomically activate
  `reports/v5_active_window.json`,launch only the registered control from H8,verify
  manifest identity,and pass post-start canonical rearm survival. During the active
  window only exact locked H10 lifecycle processes and the unchanged Path-1 job are
  allowed. Official hands remain0.

The CAL-complete/H10-registered section below is historical and cannot override this
ready-to-launch state.

## Authoritative operational update: CAL-EXT complete; post-CAL H10 registered

- DRIVE-TO-L5 v2 remains active. The immutable terminal bar is unchanged: one exact
  frozen V5-lineage checkpoint, official greedy-direct Slumbot, at least100,000 hands,
  bb/100>0,95% CI lower>0,and a complete audited hand bundle. Cross-checkpoint
  aggregation is forbidden.
- `CAL-EXT-001_H8_TREATMENT_GREEDY_QUICK5K` is terminal
  `PASS_COMPLETE_BUNDLE`. Completion SHA
  `04eb29d61f73031d943ee6dc098f596c145515d8faf17ae30255259abe693019`
  and audit SHA
  `098a5e5946ecad263cd6a42fb6a62c09849aa457d046526a82125050f37a9679`
  PASS40/40 bind exact H8 endpoint iter33834 /556,011,085,checkpoint SHA
  `7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`,
  official greedy-direct,4x1,250=5,000 hands,32,060 decisions and parse errors0.
  Result is `-207.1804 bb/100`,95% CI `[-297.6644,-116.6964]`,L0. Artifact audit,
  hand review and selector replay pass. The sole promotion-gate FAIL is the expected
  `promotion_hands` check. This pays external debt but is calibration-only:it cannot
  reclassify H8/H9 or prove a method,V4,L5 or L6 claim. Point and CI upper below-100
  flag severe external weakness;promotion20k is not authorized.
- Post-CAL Route Review006 result SHA
  `6420251b4e1ab8c54f8935dc375beea04c2038e3a8e2a69f432111a091e49bfe`
  and audit SHA
  `08873349008b7c03ea8fd8c9853017af86850443aaef8b404922f6b7eab77368`
  PASS32/32 select a new clean H10 and set `route_exhausted=false`. CAL loss cuts
  (BB raise99.1%,call0.1%) remain observational and do not authorize action tuning.
  H7/H8 instead supply controlled critic-MSE/KL-instability evidence;H9 supplied no
  SmoothL1 evidence. Path-1 is healthy204/600 but incomplete,diagnostic-only and not
  V5.5-training eligible.
- New post-CAL H10 preregistration SHA
  `cf562528360e05e4683bc3bd04edc19ba49ea98c2a2ddeb4d92f45805eab11fc`
  and audit SHA
  `e8acde7136fa552ef0a2587b20b8ac0c0fedea0e322686afe1931abc665e7744`
  PASS30/30. It freezes fresh20260715 same-start fixed20M control then treatment from
  the canonical H8 endpoint. The sole variable is catch-up value loss MSE versus
  SmoothL1 beta1.0 raw critic-v1 bb;all H9 config and statistical gates remain exact.
  The source is a controlled training source,not an external model candidate. H9
  partial and CAL benchmark-copy paths are forbidden. Status is
  `REGISTERED_NO_LAUNCH`:next is implementation+identity audit,immutable design lock,
  preflight and canonical rearm. No H10 arm may launch before all pass.
- H9 remains permanently `INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`;no resume,
  completion,reclassification or partial-checkpoint use. During an H10 arm all
  Slumbot/mirror/evaluator and unregistered project-script execution is forbidden.
  Path-1 may only continue its existing six BelowNormal CPU workers;no restart,
  expansion,ingestion or GPU use.

The goal-v2 pre-CAL section immediately below is historical and cannot override this
update.

## Authoritative operational update: DRIVE TO L5 v2 / CAL-EXT-001 required

- User goal v2 is active and supersedes every mutable H9-running instruction. Activation
  artifact `reports/v5_campaign_goal_v2_activation_20260715.json` freezes the source
  directive, H9 terminal evidence, external-debt computation and next transition.
- H9 is permanently `INCONCLUSIVE / H9_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`.
  Judgment SHA256
  `dd1ada4c08058b2d479b5b8fa80b6c0880df71c49b70b6d0fc401c1e562d3fe6`,
  terminal audit SHA256
  `54d782f684dd091e4e095537231a9bfdee6575714341b4baef0476800cc02ee2`
  and incident SHA256
  `e2f1acc0f32f0cffd3fa9b31a3da040b44977a2c0cf9ee40016f255d548d3fa6`
  are immutable. H9 cannot resume, extend, reclassify, launch treatment/mirror/evaluation,
  or support a SmoothL1 method or strength conclusion. Its partial checkpoint is
  diagnostic-only and forbidden as a successor source.
- `EXTERNAL_DEBT_GATE` is due: latest complete official greedy-direct checkpoint has
  504,474,081 training hands; exact clean H8 treatment endpoint has 556,011,085, a debt
  of 51,537,004 hands, exceeding the hard 50M maximum. No behavior window may launch
  until `CAL-EXT-001_H8_TREATMENT_GREEDY_QUICK5K` completes its full audited bundle.
- CAL-EXT-001 must freeze exact H8 treatment endpoint iter33834 /556,011,085, SHA256
  `7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`,
  official greedy-direct, 4 sessions x1,250 hands, no adaptive extension or later
  checkpoint substitution, and all hand/dump/CI/gate/analysis/loss/audit/review artifacts.
  It is `EXTERNAL_STAGED_CALIBRATION_ONLY`: it cannot reclassify H8/H9 or prove V4/L5/L6.
- The pre-CAL Route Review006 result SHA256
  `f9aa625c8209c78662d1ac687f595d94e37a57c755f597923c2a9b1eb2467a4b`
  and H10 preregistration SHA256
  `9ca522b4a84b3cc0daa5a3ad326d87ebfa909a064c4ce36cb92284b34152b6a1`
  remain preserved but are `SUPERSEDED_PRE_CAL_EXT` and grant no route or launch
  authority. A new post-CAL Route Review006 must include CAL-EXT-001 before any H10.
- Method verdict, model candidacy and strength claim are separate. Only one exact frozen
  checkpoint with official greedy-direct 100k+ hands, bb/100>0, CI lower>0 and a complete
  bundle can establish L5; cross-checkpoint aggregation is forbidden.
- During any active trainer arm, no delegated task may execute project scripts. Delegated
  work is limited to file reads, hashes and process listing; commands containing Slumbot,
  mirror or evaluator process tokens require exact design-lock authority.
- The stale H9 reporting watchers PIDs32712/49972/49008 were retired after terminal
  verification; no trainer or behavior changed. Heartbeat `v5-drive-to-l5-monitor` remains
  paused during incident containment. Path-1 coordinator37656 and six CPU-only workers
  remain detached diagnostic-only; do not restart, expand, ingest or move them to GPU.
- Latest official strength remains L0:20,400 greedy-direct hands,-153.2999 bb/100,
  CI[-187.6945,-118.9052].

The H9-running section immediately below is historical and cannot override goal v2.

## Authoritative operational update: H9 control running (2026-07-14)

- The standing `ACTIVE_DRIVE_TO_L5` campaign and immutable L5 claim bar remain active.
  H9 preregistration SHA256
  `05bcb04a34cff546cce2159ecdee3e31850c54e0f8a9f37accb30090a100f84b`,
  design-lock SHA256
  `30071df4fa72ddf9c4244eace4e9ed4cbe8186d7e3c53d93fde0f2044687d81e`
  and preflight SHA256
  `79d84c38264153f37ed53c88a4f05818788a9aacec62647fcb0f62dd97f6aac6`
  are authoritative PASS artifacts. The frozen 40k mirror measurement lock SHA256 is
  `db03a3da23de56ce2a96fe06e4247041d9ec26c99fe3da76d2d51745e4477b34`.
- Fresh control `v5_hybrid_h9_control_catchmse_same33834_20m_r1_20260714` is running
  as PID49380 from exact H8 treatment endpoint iter33834 /556,011,085,checkpoint SHA256
  `7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`.
  Its fixed target is576,011,085;optimizer is preserved,target-KL0.03,catch-up is enabled,
  and the control catch-up loss is MSE. Treatment will change only that catch-up loss to
  SmoothL1 beta1.0 after the control endpoint freezes PASS. Health is PASS,protocol is
  `ARM_RUNNING_GUARDS_PASS`,resource-isolation violations0 and stderr is empty.
  Registered control first60 is frozen `PASS_CONTROL_BASELINE_FROZEN` at
  `2043.778818` effective h/s using rows2..61. This is a throughput baseline only;
  control continues to the fixed endpoint and treatment must achieve ratio>=0.85.
- Canonical rearm status SHA256
  `5892f447266b48b23c22cb20859ea8533a463dc512ae02995f583c077882656d`
  has `survival_pass=true`;endpoint,protocol,treatment-launch and completion supervisors
  are alive and all generic/internal/Slumbot paths remain terminally blocked.
- Thread heartbeat automation `v5-drive-to-l5-monitor` is ACTIVE at a30-minute cadence.
  It only wakes this task to reread exact artifacts and continue registered transitions;
  it launches no trainer,watcher,solver,mirror or Slumbot job and must be removed after
  L5 PASS or route-exhaustion escalation. Do not create a duplicate heartbeat.
- A reporting-only startup adapter omission was CENSUREd and corrected without touching
  trainer PID49380. Correction artifact SHA256
  `5921093568c5f1839e1ea120f84cfe6d804f9776e03a5966c10c8d6aeda25c4d`;
  failed mutable status/log snapshots were preserved;focused tests22/22 PASS. The adapter
  now removes only the already-existing `vhcatch=` reporting token for correct H9
  identities, allowing the unchanged frozen monitor to report health PASS. No behavior,
  lock,gate or strength authority changed.
- A second pre-cutover control-plane audit prevented a future duplicate completion
  supervisor during treatment rearm. Correction artifact SHA256
  `adbd0dd26e5a7e8b3480444fc4e869a1b48c40825f5f976874d63ad4b34e9db5`
  patches only the intentionally non-locked exact treatment launcher: after treatment
  manifest identity PASS it retires the unique control completion supervisor, fails
  closed on duplicates, then invokes the unchanged canonical rearm. No duplicate or
  treatment existed at correction time;trainer,design lock,behavior and gates are unchanged.
- Locked post-arm chain static audit SHA256
  `c7d914802ef3a991117b215bedc1a2e9771750ae305667dd0c4ebfa16c3ef35a`
  is PASS:measurement-lock,manifest,mirror/completion/judge tool bindings and exact
  H8 source-anchor identity all verify. `source_anchor` is the semantic checkpoint role
  and `anchor` its immutable evaluator arm alias;hash/iteration/hands are identical.
  No mirror output may start before both H9 endpoints freeze PASS and no trainer is active.
- H9 authorizes official hands0. Latest official strength remains L0:20,400
  greedy-direct hands,-153.2999 bb/100,CI[-187.6945,-118.9052].
- Path-1 remains detached diagnostic-only and was not touched, restarted or expanded.
  Immutable progress audit SHA256
  `2b1e1a18cb1797a56a1e14d96adfbc477e7134a552534cecc32d946a3e88583`
  PASSes at136/600 complete gzip/meta pairs:all136 latest unique QA records PASS,
  illegal post-all-in rows0,missing/bad metadata0. Historical board211 FAIL remains
  preserved and its latest replacement PASS. Coordinator PID37656 remains BelowNormal
  with six CPU workers;the asset is not v5.5-training eligible and consumed zero
  official hands.

The older H9 registered-no-launch and H8 sections below are historical.

## Authoritative operational update: H8 terminal FAIL; H9 registered (2026-07-14)

- H8 is terminal `FAIL / H8_FAIL_REGISTERED_GATE`. Judgment SHA256
  `2436b8eccf095408b55a1f0357f6f85fbf1eb8936c7fe621adccc0e815efc384`
  and independent audit SHA256
  `5202c63c7f54e355b2f7770662a8a3fc22a22db17e7c4a7d0899b12acceb3764`
  are immutable. The fixed40k mirror strongly passed, but primary critic MSE, source
  anchor calibration and both KL-stability gates failed. H8 is not adopted, extended
  or reclassified and authorizes no official hands.
- Route Review 005 result SHA256
  `49ae4ac04ecaa48cbd4ea3c8acecd3f29c9a92a5516a0deffd73b7e7c53c6956`
  is `PASS_ROUTE_REVIEW`, `route_exhausted=false`, and selects
  `H9_ROBUST_VALUE_HEAD_CATCHUP_LOSS`. The sole prospective change is catch-up-only
  MSE to SmoothL1 beta1.0 raw bb; standard PPO critic MSE,target-KL,targets,epochs,
  optimizer and actor/trunk remain unchanged.
- H9 is exactly `REGISTERED_NO_LAUNCH`. Preregistration SHA256
  `05bcb04a34cff546cce2159ecdee3e31850c54e0f8a9f37accb30090a100f84b` and audit
  SHA256 `43c2e9a4b48ec35f6c5408547108f25986adc8c6e805a3b53eb815a399dc228f`
  PASS22/22 freeze fresh same-start fixed20M arms from the H8 treatment endpoint.
  Next is implementation plus bitwise/isolation tests, independent audit, immutable
  design lock, preflight and canonical rearm; no arm may launch before all pass.
- Latest official strength remains L0:20,400 greedy-direct hands,-153.2999 bb/100,
  CI[-187.6945,-118.9052]. H9 authorizes official hands0.

The older H8 evaluation-running and treatment-running sections below are historical.

## Authoritative operational update: H8 locked evaluation running (2026-07-14)

- Both H8 arms are now frozen endpoint PASS and no H8 trainer is active. Treatment
  `v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714` finished naturally
  at iter33834 /556,011,085 hands, registered overshoot9,799<=50,000, stderr0 and
  official hands0. Frozen checkpoint SHA256
  `7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`;
  endpoint-status SHA256
  `de4913626d117aac50f2c09084cf636f9b08232a82dfeb8e33cbcb68d099dfb2`
  PASS; protocol-status SHA256
  `5e265c087a9c4a8ebf1090695a879cea139ad2b556ad86d6ca4b2e908cfb6b7a`
  is `ARM_FINISHED_GUARDS_PASS` with 1,217 rows, first60 ratio0.8743871084 and
  isolation violations0.
- The locked completion supervisor has valid evaluation authority and is running the
  control fixed40k common-deal mirror CPU-only/BelowNormal/threads1 under measurement
  lock SHA256 `9b48175c3c65144f34c4ca64a678fd9311c54c4a522e4fa18c51b740caae0053`.
  It must complete the registered control/treatment/anchor mirror, immutable audit,
  forbidden holdout comparison and terminal H8 judgment without adaptive extension.
  No method verdict exists yet and H8 still authorizes zero official hands.

The older H8 treatment-running section immediately below is historical and cannot
override this evaluation-running update.

## Authoritative operational update: H8 treatment running (2026-07-14)

- The standing `ACTIVE_DRIVE_TO_L5` campaign and immutable L5 claim bar remain active.
  H8 preregistration SHA256
  `ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713`
  and design-lock v5 SHA256
  `298daa368585af79586f3ba24b7fde1ae862de41a8221cdf46c0825d041957c6`
  remain authoritative.
- Control `v5_hybrid_h8_control_kles003_nocatch_same32617_20m_r1_20260714`
  is terminal endpoint `PASS`: iter33834 / 556,010,507 hands, registered overshoot
  9,221 <= 50,000, stderr empty, protocol PASS and official hands0. Frozen checkpoint
  SHA256 is `29b72c27a704b631297296025a542217c4cba1512d90e40ad3cd3da5383702d8`;
  endpoint-status SHA256 is
  `65d6ffedd41f459bbe21beb116a6d016964b6739c64a7d194b0c810eeb750db2`.
  Its registered first60 baseline remains 2268.809632 effective h/s.
- Exact treatment `v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714`
  is running as PID40760 from the same frozen H7 source iter32617 / 536,001,286,
  source SHA256
  `948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149`.
  Its fixed target is 556,001,286; optimizer is preserved, target-KL remains0.03, and
  the sole registered treatment variable is `value_head_catchup_after_kl_stop=true`.
  Current health and protocol guards are PASS, stderr is empty, and resource-isolation
  violations are zero. Treatment first60 is frozen PASS at 1983.817894 effective h/s;
  ratio `0.8743871084 >= 0.85` versus the control baseline. Immutable bundle status SHA256
  `bedd4575defbd769227f568530f375409686b5a6d9538f2ec053f877d2aad918`,
  metrics SHA256 `8475b9955b214cc74af2082cc500736763b9b6026c0b8eb8731fdbaa67d078b5`,
  audit SHA256 `e07794e74a27305bda1055ce6e4e3a6305b60a99a1a0dd954449680e50bb1066`.
  This passes only the registered protocol throughput gate and is not method or strength
  evidence; treatment continues to its fixed20M endpoint.
- Canonical treatment rearm status SHA256
  `d55f77f5577c1701e25053bf00debf472b8bf16ba7c0ee4d1b521a7f1332ba8c`
  has `survival_pass=true`; health/dashboard/Ops/archive/endpoint/protocol/completion
  watchers are alive. Eight generic, cadence, internal, EXP-003 and Slumbot paths remain
  terminally blocked. No endpoint evaluation may run while the treatment trainer is
  active, and H8 still authorizes zero official hands and no strength inference.
- A one-shot control-side launch supervisor remained in `INVOKING` after the exact
  treatment and canonical rearm were already materialized because a Windows conhost kept
  the captured pipe open. The stale state was preserved, only the one-shot supervisor
  was stopped, and the immutable locked script was not edited. Correction artifact
  SHA256 `5ba7c629662fccb81fcfa733f2ffa610766f565ca444dd22928407a1e9c93a49`;
  recovered launch-status SHA256
  `4550361e2401d815508fd60c79d979fd5987467732f5f844b5abdb60816713c5`.
  This is reporting-only and changes no behavior, gate or judgment authority.
- The treatment protocol watcher later exited on a Windows atomic status-file replace
  race. Trainer, endpoint and completion supervision remained alive. Canonical
  idempotent rearm restored protocol PID33728 with `survival_pass=true`, current guards
  PASS and stderr0; the locked watcher script and H8 design lock remain unchanged, and
  post-rearm lock audit SHA256
  `b848ab3171270ddecc7745da8e30b2b4a4bf3f1f443cfe057f39725b875b7f09`
  is PASS. CENSURE artifact SHA256
  `6c663d00662593113edce5dc3ce3ec8286415f9d6ea75b0f36bec346e1006034`
  explicitly records that the mutable pre-rearm stderr/status was not separately
  snapshotted before canonical rearm recreated it. This changes no behavior, gate,
  endpoint evidence or judgment authority.
- Path-1 remains untouched at its immutable 121/600 QA-PASS progress artifact SHA256
  `cdbf77e13f011413fc6a3fff7f8686e688da493b78d82aa8d19b959019dbfe52`,
  coordinator37656, six CPU-only/BelowNormal workers. It is diagnostic-only and not
  v5.5-training eligible. There are 121 complete gzip/meta pairs and all121 latest
  per-board QA records PASS with zero illegal post-all-in rows; the preserved historical
  board211 FAIL remains audit history and its replacement is PASS.
- Latest official strength remains L0: 20,400 greedy-direct Slumbot hands,
  `-153.2999 bb/100`, 95% CI `[-187.6945,-118.9052]`.

The older H8 control-running section immediately below is historical and cannot override
this treatment-running update.

## Authoritative operational update: H8 v5 control running (2026-07-14)

- The standing DRIVE-TO-L5 objective and immutable L5 claim bar remain active. H7 is
  terminal FAIL; Route Review 004 remains `PASS_ROUTE_REVIEW`, `route_exhausted=false`,
  and H8 is the selected next single-variable window.
- H8 preregistration SHA256
  `ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713`
  is unchanged. The authoritative superseding design lock is v5, SHA256
  `298daa368585af79586f3ba24b7fde1ae862de41a8221cdf46c0825d041957c6`;
  audit SHA256 `9670eb758ed13abe58e96f01dc2cbd6b511163492b2420d01aff45e2f8ae44c5`
  is PASS and preflight SHA256
  `d6efa5aac05389e0c52b718bfb888faed87813c06ea4a7f348d4dcbfa7f051bd`
  is `PASS_READY_H8_CONTROL_LAUNCH`.
- Exact control `v5_hybrid_h8_control_kles003_nocatch_same32617_20m_r1_20260714`
  is running as PID `45144` from the frozen H7 treatment endpoint iter32617 /
  536,001,286 hands, SHA256
  `948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149`.
  Target is 556,001,286 hands; optimizer state is preserved, target-KL remains0.03,
  and control catch-up is false. Launch-result SHA256
  `141f7303ff69d1f5d1f49bdfa342834d5d2f71c8bda69950d04bf0ed01f6cdd7`.
- Canonical rearm survival is PASS with eight permitted watchers alive. Generic gate,
  eval cadence, internal probe, EXP-003, promotion20k and formal100k paths are all
  terminally skipped for this H-window. Protocol state is running with zero resource
  isolation violations, empty trainer stderr and official hands0. The duplicate-safe
  watcher will launch treatment only after the exact control endpoint and first60/full
  protocol prerequisites pass.
- A reporting-only parser incompatibility was corrected and CENSUREd. The frozen
  `v5_monitor.py` SHA256
  `fb7ed628e2a2d246d5094fb1882465c42ac11768ed6a0bcec2ebab05ebd034a4`
  is unchanged; an H8-only shadow view removes solely the new `vhcatch=0/1` log token,
  retains exact source provenance and now publishes health `PASS`. The prior WARN is
  preserved read-only. Tests are 25/25 PASS, lock re-audit SHA256
  `5c3b04b5ea9f9762c8bd9e2c53a15d316f73dcfaf2c06ceaceb1c6ef63fe3821`
  remains PASS, and canonical rearm again has eight permitted watchers alive with all
  eight generic/Slumbot paths blocked. The treatment-launch PowerShell token-spacing
  defect was also corrected outside the lock. Correction artifact SHA256
  `86bfea852188b1e9972ae0854c50f9194b44b757e9c9745d18e0ff65a64eba1d`.
- A later one-poll WARN exposed a second reporting-only race: after parsing a valid live
  manifest, the adapter separately copied it while the trainer was rewriting the file.
  The next canonical poll recovered PASS without forcing. The adapter now retries one
  parseable read and atomically writes that exact snapshot; tests are 26/26 PASS,
  canonical rearm is survival PASS, and frozen monitor/lock evidence remain unchanged.
  Correction artifact SHA256
  `b377b09444a5237f98fb61a6ffb9ed3dc1fbeed230c298892e1311b1a221fd2d`;
  post-correction lock audit SHA256
  `9892a871260169081e38cf3ee07f03e4974c400c94ad0c2a186774dddf625e52` PASS.
- The control first60 baseline is now frozen PASS at `2268.809632 effective h/s`, using
  exact metrics rows2..61. Immutable first60 audit SHA256
  `88e2ae08c35d564e613b32b5371114c9985939f2bf3df7ea0ec9dc9940987e32` is
  `PASS_IMMUTABLE_H8_CONTROL_FIRST60`. Control continues to the fixed20M endpoint;
  this is protocol evidence only, not strength evidence.
- A prior v3 startup attempt is terminal
  `H8_CONTROL_STARTUP_PROTOCOL_ABORT_GENERIC_REARM`, preserved read-only and forbidden
  for endpoint, method or strength evidence. Incident SHA256
  `8819440d3b39df3ee1af2d6869232baeafa65a2298806d6abd7f0f50df0d0ab2`.
  It launched no Slumbot hands. V4 was never launched and was superseded after its
  preflight correctly failed closed on a non-worker child-classification defect.
- Path-1 remains the same detached diagnostic asset job: coordinator PID `37656`, six
  exact `solve-worker.ts` workers, CPU-only/BelowNormal. Its direct `conhost.exe` child
  is excluded from worker count. Read-only progress is now 103/600 complete gzip/meta
  pairs, all103 latest QA records PASS with zero illegal post-all-in rows; historical board211 QA-FAIL
  was automatically preserved and re-solved to PASS. Progress artifact SHA256
  `386bf342183aa70b8afa4090db2f513a8794816ad875c39d0d197f4f563090f1`.
  The job was not restarted, expanded or modified and remains diagnostic-only.
- Latest official strength remains L0: 20,400 greedy-direct Slumbot hands,
  `-153.2999 bb/100`, 95% CI `[-187.6945,-118.9052]`. H8 currently authorizes zero
  official hands and no V4/L5/L6 inference.

The older H8 `REGISTERED_NO_LAUNCH`, no-process, and H7-running paragraphs below are
historical snapshots and cannot override this update.

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
