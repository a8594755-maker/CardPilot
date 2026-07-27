# CardPilot Agent Workflow

## Current Objective

Reproduce and extend AlphaHoldem for 200bb heads-up no-limit Hold'em with an end-to-end RL agent. The reference paper is Zhao et al., "AlphaHoldem: High-Performance Artificial Intelligence for Heads-Up No-Limit Poker via End-to-End Reinforcement Learning," AAAI 2022.

Primary target: beat Slumbot at 200bb. A valid win claim requires at least 100k Slumbot hands, bb/100 > 0, and 95% CI lower bound > 0. The stretch target is near the paper result: about +11.1 bb/100 vs Slumbot.

Do not claim V4/L5/L6 strength from training health, self-play reward, 2k diagnostics, or 5k quick screens.

## Operating Precedence And Document Hygiene (effective 2026-07-22)

This section and the adaptive-research sections immediately below are the current
governance policy. They supersede conflicting historical workflow, cadence, autonomy,
and recovery language later in this file. They do not alter an immutable terminal
scientific result, weaken the L5/L6 claim bar, or authorize reuse of a closed attempt.

Use this order when deciding what to do:

1. Current user and platform instructions.
2. The immutable objective and research constitution in this file.
3. The topmost and therefore latest authoritative operational update in this file.
4. Exact identity-bound artifacts and the append-only experiment ledger.
5. Historical updates and legacy operating sections, which are evidence only.

An older PID, checkpoint, cadence target, next step, or `do not launch automatically`
clause is not a permanent command after a newer user governance decision and current
state supersede it. Preserve the historical text and artifacts; never replay the old
operation. Historical process IDs, `Latest Takeover Handoff`, old `Evaluation Cadence`
targets, and old intervention postures are stale unless the latest authoritative update
explicitly revalidates them.

Keep AGENTS.md focused prospectively on the constitution, adaptive policy, and one
topmost authoritative current-state update. Preserve detailed chronology in append-only
ledgers, reports, and snapshots. Future refreshes should replace or prepend only the
compact current-state update and a history pointer rather than copying another full
operating manual into this file.

## Research Constitution

The project is optimized for externally demonstrated poker strength, not for audit
PASS counts, self-play volume, training health, documentation volume, or the number of
closed windows. Audits and control-plane checks are enabling controls; they are not
scientific progress by themselves.

The agent must behave as a constrained researcher:

- Maintain a ranked set of falsifiable hypotheses across the four non-V6 route
  families: critic/target design, exact-V5.5 CFR/BC teacher warm-start, opponent league,
  and play-time resolver.
- Prefer the smallest upstream intervention that can distinguish the leading causal
  hypotheses, while allowing one coherent intervention to contain inseparable changes
  required by that hypothesis. `One behavior-affecting change` means one causal
  intervention, not necessarily one scalar coefficient.
- Re-rank or replace hypotheses before registration when new frozen evidence warrants
  it. Never redesign a registered window after launch.
- Use Slumbot as the primary external directional signal and the sole formal strength
  authority. Use internal probes, teacher holdouts, loss cuts, and training metrics to
  localize mechanisms, not to substitute for external evidence.
- Spend research effort in proportion to information gained. Do not create another
  audit/review layer when a smaller deterministic contract test answers the same
  control-plane question.

The agent may autonomously progress through registered boundaries within the four
non-V6 routes after a compatible active goal or direct user instruction authorizes the
campaign. Escalation remains required for V6 architecture/observation redesign,
changing the objective, claim bar, or official greedy-direct policy, spending money,
secrets, destructive action, or scientific exhaustion of all four routes.

## Adaptive Research Loop

Every behavior/model-changing program follows this closed loop:

1. Establish the exact current checkpoint, latest complete external evidence, current
   structural leaks, route state, and unresolved blockers.
2. Build an evidence matrix separating realized-loss localization, association,
   counterfactual evidence, same-start method effects, and formal external strength.
3. Rank falsifiable hypotheses and select one coherent intervention with an explicit
   reason it should change external play.
4. Preregister its source identity, budget, primary and secondary outcomes, external
   evaluation trigger, abort criteria, rollback, and interpretation rules.
5. Implement and validate proportionately to risk. Behavior changes, training-data
   generation, and official evaluations require independent audit. Pure read-only
   reporting and reversible control-plane work may use deterministic automated contract
   tests unless an existing immutable registration explicitly requires more.
6. Run the bounded window once and judge it exactly as registered.
7. If the window changed model behavior and reached a valid endpoint, run the required
   external screen before starting another behavior window.
8. Retain, roll back, change hypothesis family, or declare that route scientifically
   exhausted. Record the decision and refresh the topmost current-state update.

No new self-play budget is justified merely because the trainer is healthy. A
continuation must identify what new information the additional hands will provide and
the external checkpoint at which the hypothesis will be tested.

## External Slumbot Evaluation Cadence

Separate research feedback from formal claims:

- Run one complete greedy-direct quick5k Slumbot diagnostic after every completed
  behavior-affecting training window and after every new BC/distillation checkpoint
  that is eligible to seed RL. Do this before another behavior window begins.
- During a longer unchanged training window, do not add more than 20M self-play hands
  between frozen quick5k checkpoints unless the preregistration fixes a shorter cadence
  or a documented external outage makes the screen impossible.
- Do not rerun Slumbot after reporting-only, audit-only, interface-only, or teacher-asset
  work when no deployable checkpoint changed. Such a run cannot measure the effect of
  that work.
- Quick5k is directional elimination/screening evidence only. It may reject a route or
  trigger a preregistered follow-up when combined with consistent structural evidence;
  it never proves improvement, V4 strength, L5, or L6 by itself.
- Promote to 20k only through a preregistered gate using the quick5k result plus the
  relevant mechanism/quality evidence. Launch formal100k only when the frozen 20k
  evidence makes L5 statistically plausible under a preregistered rule.
- Every screen retains hand JSONL, decision dump JSONL, CI, promotion decision, loss
  report, artifact audit, and hand review. An incomplete bundle is no result.

The absence of a new checkpoint is a valid reason not to run Slumbot. `A 5k screen
cannot support a strength claim` is never a reason to omit the next required directional
screen after model behavior changes.

## Failure Taxonomy And Recovery

Classify failures before selecting the next action:

1. **Scientific failure.** A valid experiment or structural proof falsifies the
   registered hypothesis or design. Freeze the result, never rerun that exact window,
   and re-rank the remaining route hypotheses.
2. **Pre-output control-plane failure.** No behavior, scientific rows, or official hands
   were produced, and the failure is a path, invocation, identity, launcher, or checker
   defect. Preserve the failed identity permanently. A single corrected attempt may be
   created under a fresh preregistration, fresh code/output/seeds where applicable, and
   independent audit without an intervening route review when the correction cannot
   alter the scientific design. It is a new attempt, never a repair or rerun of the
   terminal identity. A second recurrence forces workflow-simplification review.
3. **Inconclusive evidence.** Do not force PASS or FAIL. Re-rank based on expected
   information gain and do not extend samples post hoc.
4. **Evidence-bundle failure.** Preserve the incomplete run. Derived reporting may be
   rebuilt only from complete immutable raw evidence; missing or corrupt hand/decision
   evidence requires a fresh registered evaluation rather than reconstruction.

A structurally impossible design, such as quotas assigned to unreachable game-state
cells, is a scientific design failure rather than a control-plane typo and cannot use
the one-correction rule.

## Meta-Review And Progress Guards

- After two consecutive scientifically valid behavior windows fail to improve their
  preregistered external directional criterion, stop local coefficient tuning and run a
  meta-review that must switch or fundamentally revise the hypothesis family.
- After three consecutive control-plane-only terminal closures or three consecutive
  nonbehavioral boundaries without clearing the named scientific blocker, simplify the
  workflow before adding another layer. Identify the repeated root cause, delete no
  evidence, and reduce the number of prospective boundaries/checkers.
- A nonbehavioral step is justified only when it clears a named blocker for a ranked
  hypothesis and has an exit criterion. Audit completion alone is not an exit criterion
  for the research program.
- Each topmost current-state refresh records the latest official Slumbot result; last
  externally screened checkpoint; last behavior change; ranked hypothesis and blocker;
  next behavior/external trigger; consecutive no-progress behavior windows;
  consecutive control-plane/nonbehavioral boundaries; and remaining route families.
- Route exhaustion is scientific, not administrative. It may be declared only after all
  four non-V6 route families have frozen evidence showing that no viable correction
  remains within scope.

Current authoritative update (2026-07-22 12:43 EDT): Phase FA Design Revision006
preregistration/audit SHAs
`c7f3645b7c1f763bd37ab99149c72f2b697868199735e80ebc36be4df16efd42` /
`976c2721545f8aef7cc69167c9328531f55edc566f134fe31c741112b5d891b0`
PASS267/267 establish
`PHASE_FA_DESIGN_REVISION006_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_Q006_IMPLEMENTATION_READY_ONLY`.
Revision006 replaces target-cell search and the failed global census with one fresh,
bounded300k-state legal-trajectory pilot(100k each at200/100/50bb). It accepts actual
reached acting-player information sets only;all legal proposal actions retain positive
probability. A line stratum becomes quota-eligible only when the immutable pilot
observes >=256 unique information sets and >=64 public replays. Absent/ineligible
strata receive no quota,no synthesized state and no cross-fill. The pilot must cover
all24 depth/street/actual-actor base cells,>=6 eligible line buckets per depth and all8
globally. MC32 remains exact-V5.5 4x8 with fresh hidden-card/deck determinization per
rollout,6144 balanced quality states,768 exact repeats,zero leakage/identity/illegal-
mass failures and registered stability/resource gates. A PASS deterministically derives
the frozen20M quota manifest from90% pilot frequency+10% uniform eligible-line coverage;
no post-output quota adaptation is allowed. The prospective path is one qualification,
audited quota manifest,eight asset windows,one BC checkpoint,teacher/legality gates,
then mandatory greedy-direct quick5k before another behavior window.

Latest complete external screen remains CAL-EXT-002 on the frozen H11 checkpoint
iter35051/576,021,901:5,000 official greedy-direct hands,-146.1726bb/100,95%CI
[-238.5979,-53.7473],L0. Revision006 changes no checkpoint,so Slumbot is not due now;
the next trigger is the first eligible frozen BC checkpoint. Ranked hypothesis is the
exact-V5.5 trajectory-native teacher route;the named blocker is whether reachable
support,MC32 label quality and the all-20M resource projection pass prospectively.
Current-policy no-progress behavior windows=0;post-simplification nonbehavioral
boundaries=1;all four non-V6 families remain scientifically open;route_exhausted=false.
Next is one separately registered Q006 implementation plus independent implementation
audit only;stop before ContractProbe,qualification,support discovery,quota manifest,
asset,training,GPU,evaluator,Slumbot,checkpoint,H19/later behavior or official hands.

The 2026-07-22 12:33 update below is historical.

Current authoritative update (2026-07-22 12:33 EDT): Route Review031 result/audit
SHAs `b40a5b7fb689ebcf5f86bbff7c2c8563b0c891ac36de94bb8c65db4592fe21d8` /
`2437302b54f4937b721d06a10716834669414ed5b8d25ae4c05dc9b808c48fb3`
PASS98/98 establish
`ROUTE_REVIEW031_PASS_SELECT_REVISION006_ROUTE_NOT_EXHAUSTED`. All four non-V6
families remain scientifically open. The teacher route has the highest information
gain because PCV019 proves the exact-V5.5 interface while Revision003 and Design
Review004 close only Cartesian zero-shortfall cells and the600s exhaustive global
support census. The selected next candidate is
`PHASE_FA_DESIGN_REVISION006_TRAJECTORY_NATIVE_REACHABLE_STATE_TEACHER_WITHOUT_GLOBAL_SUPPORT_CENSUS`.
Revision006 must generate legal trajectories directly,label only actually reached
acting-player information sets,resample hidden information per MC32 rollout,freeze a
bounded support-discovery pilot before final quotas,and define a bounded path through
asset,one BC checkpoint,teacher/legality gates and mandatory greedy-direct quick5k.
Workflow simplification removes the global census,Cartesian impossible cells,exact-CFR
schema branch and repeated interface-smoke chain. Route exhaustion is false. Next is
one separately registered Revision006 design preregistration plus independent
preregistration audit only;stop before implementation,support discovery,qualification,
asset,training,GPU,evaluator,Slumbot,checkpoint,H19/later behavior or official hands.
No deployable checkpoint changed,so external trigger remains `NO_NEW_CHECKPOINT`;L0.

The 2026-07-22 12:27 update below is historical.

Current authoritative update (2026-07-22 12:27 EDT): Route Review031 preregistration
SHA `3598c0bffad7ea4a29940e4fa670eb292e42f8420c5d9c6163365d183c54a4f3`
and independent preregistration-audit SHA
`b132e126a27e47632dc0bb3544185332c6f78f82c1e76b9fe357eaf6bfd4ad09`
PASS86/86 establish
`ROUTE_REVIEW031_REGISTERED_PREREVIEW_AUDIT_PASS_RESULT_REVIEW_READY_ONLY`.
The review is a read-only route and workflow-simplification meta-review across the four
non-V6 families. It freezes Design Review004 and Revision003 terminal evidence,16/16
recomputed evidence hashes,legal-trajectory-native teacher Revision006 as the first
candidate,then opponent league,full200 resolver,a scientifically distinct critic/target
mechanism,and route exhaustion only if all four families are scientifically exhausted.
It forbids rerunning the600s census,inferring partial support,reopening Revision003,or
counting audit completion as scientific progress. No result or result audit exists.
Next is exactly one separately executed reporting-only Route Review031 result plus
independent result audit and current-state refresh;stop before any selected design,
implementation,asset,training,GPU,evaluator,Slumbot,checkpoint,H19/later behavior or
official hands. No deployable checkpoint changed,so the external-screen trigger remains
`NO_NEW_CHECKPOINT`;route_exhausted=false,L0.

The 2026-07-22 12:14 update below is historical.

Current authoritative update (2026-07-22 12:14 EDT): Design Review004 prereg/audit
SHAs b0b0daffbdcf35db7d24fc28ea980f3f4aa9e4f5f7b479637bb6ee12aba0f08a /
25abb2e4f212a1571b6ae463b7920c26868e188b415a9336a15296cd72997511
PASS91/91;result/audit SHAs
7d27cdd9891986e8c8813bc50f88bb95916140df76fff26362a65a286d03c0fb /
59d9993f48cc1c1dcd43c171234dcc2833cc5ea55fef77b5995a5b94f3d62fa8
PASS75/75 select `ROUTE_REVIEW031_REPORTING_ONLY`;route_exhausted=false. The sole
exact public-state BFS attempt exited124 after about604.019s at the frozen600s outer
wall gate before any complete three-depth census JSON or support map reached stdout;
files_written0 and no process remains. Never rerun,extend,relax,reconstruct partial
support or infer support counts. Revision005 is not selected. Revision003 remains
terminal and untouched with code/probes/qualification0. Next is separately registered
Route Review031 preregistration plus independent audit only;do not launch automatically.
No Revision005,asset,training,Path-1/protected CFR,GPU/evaluator/Slumbot/checkpoint/
H19/later behavior or official hands. L0.

The 2026-07-22 11:51 update below is historical.

Current authoritative update (2026-07-22 11:51 EDT): Phase FA Design Revision003 is
terminal
`PHASE_FA_DESIGN_REVISION003_FAIL_CLOSED_PREIMPLEMENTATION_UNREACHABLE_POSITION_CELL_CONTRACT_NO_CODE_NO_PROBES`.
Failure/audit SHAs
ee6292511091037020e3f72ed30af5ed582a2add8eac676daf80982adb213368 /
9cf5742ebff274e043cf4bc9f9ec80b85140200ea3ee6b715f553ea81a9a0c23
PASS126/126 prove at least30 of the frozen192 position cells unreachable. Preflop has
neither OPEN_ACTION_NO_BET nor CHECKED_TO_NO_BET;postflop street start is only player0
open,and the first check yields only player1 checked-to before the second check advances
the street. This makes at least4,375,000 rows,7,680 reachability states,960 quality
states and120 repeats impossible against the zero-shortfall gate. Prereg/audit SHAs
b8040e360e13bd1da0a64589688dadb188df437b4a44ba25b57f39cf3ae6cc56 /
ecef168e126f1eee7e25cc50d601719251ef1edbe24a88b72c0e0bb29f02e409
PASS320/320 remain provenance,but execution authority is CENSUREd for missing this
structural proof. No code,implementation audit,probe,qualification,output or asset was
created/run. Never implement,repair,rerun or reclassify Revision003. Next is separately
registered reporting-only Design Review004 or Route Review031;do not launch
automatically. No asset/training/Path-1/protected CFR/GPU/evaluator/Slumbot/checkpoint/
H19/later behavior or official hands. route_exhausted=false,L0.

The 2026-07-22 11:39 update below is historical.

Current authoritative update (2026-07-22 11:39 EDT): Phase FA Design Revision003
prereg/audit SHAs
b8040e360e13bd1da0a64589688dadb188df437b4a44ba25b57f39cf3ae6cc56 /
ecef168e126f1eee7e25cc50d601719251ef1edbe24a88b72c0e0bb29f02e409
PASS320/320 establish
`PHASE_FA_DESIGN_REVISION003_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_QUALIFICATION_IMPLEMENTATION_READY_ONLY`.
The sole revision replaces unsupported exact-CFR minimum/fallback with information-set-
correct exact-V5.5 MC32 for all20M rows:14M/3M/3M at200/100/50bb,192 exact depth/
street/line/position cells,eight2.5M windows and400x50k shards. CFR bucket,legacy54 and
PCV019 output rows are0. Opponent cards and unrevealed deck are resampled per rollout;
source hidden information cannot condition labels. Future Q003 must qualify49,152
reachable states,6,144 balanced4x8 MC32 quality rows,768 repeats,all-depth gates and a
fresh <=168h/<=100GB all-20M projection. PCV019 remains200bb planning reference only.
No implementation/qualification/asset path exists. Next is separately registered Q003
implementation plus independent implementation audit only,with exactly two fresh
launcher-bound zero-file probes;stop before qualification. No asset generation,
training,Q001/Q002 reuse,Path-1/protected CFR,GPU/evaluator/Slumbot/checkpoint/H19/
later behavior or official hands. route_exhausted=false,L0.

The 2026-07-22 11:18 update below is historical.

Current authoritative update (2026-07-22 11:18 EDT): Phase FA Design Review002
prereg/audit SHAs
264898115b2d342ae9a1a6beb25eedc3c8fa41b042df7f6ac25beb8dd0b6e77c /
be553f232d98ff35d57cb0aae59e9bc1ed1d0a016504073c9a61a9afc6ddc536
PASS81/81;result/audit SHAs
d07fdebddef5cad16341e8b286c872c30326657d9edf67a70c88ad41ec54ae7f /
54b8edb3ed36a17aded571521de763db49249e4ccaf2b565241f6fa43e754d1b
PASS88/88 select
`PHASE_FA_DESIGN_REVISION003_ALL_MC32_EXACT_V55_TEACHER_WITH_REACHABILITY_QUALIFICATION`;
route_exhausted=false. Read-only replay proves a design-id-only Q002 is futile:Q001's
actual bucketed200bb and legacy54dim100/50bb candidates are deterministically rejected,
giving static acceptance0/0/0 below thresholds0.20/0.10/0.10. Revision003 is design-
feasibility only:remove the unsupported exact-CFR minimum,use exact-V5.5 MC32 for all
20M rows,and separately freeze/audit all-cell reachability,all-depth quality,a fresh
all-20M resource bound and projection-free9-slot identity. PCV019 is200bb smoke only;
prior runtime arithmetic is planning only. Next is separately registered full
Revision003 design preregistration plus independent preregistration audit only. Do not
implement,qualify,generate assets,train,repair/rerun Q001,touch Path-1/protected CFR,
launch GPU/evaluator/Slumbot/checkpoint/H19/later behavior or official hands. L0.

The 2026-07-22 11:02 update below is historical.

Current authoritative update (2026-07-22 11:02 EDT): Phase FA Q001 is terminal
`PHASE_FA_Q001_FAIL_CLOSED_PREOUTPUT_DESIGN_ID_ENTRY_GATE_NO_RESULT_NO_RERUN`.
Exactly one Qualification attempt exited1 after0.5576639s before output:prereg design_id
is PHASE_FA_FULL_TEACHER_ASSET_DESIGN_V1 but immutable runner line639 expects
PHASE_FA_FULL_EXACT_V55_TEACHER_ASSET_20M_DESIGN_V1,then line640 raised
design_audit_classification_mismatch. Exactly one launcher-owned Audit exited1 after
0.4300681s because result.json was absent. Failure/audit SHAs
977a3556f63d4d76a9144ce418cfed4e4f9d351bb0026874333aa2ce34a1a0be /
b18176159fad590bf7114f9ce31c6498c13f0a0f88a46e751082c9ce7060570d
PASS56/56 bind code/design identities,attempts,output absence,mapper candidates0,MC32
states/rollouts0,teacher rows0 and no live process. This is control-plane evidence only:
no mapper/MC32/resource/asset/method/behavior/strength inference. Never repair-in-place,
rerun either attempt,reconstruct or reclassify. Next is separately registered reporting-
only Phase FA Design Review002 or Route Review031;do not launch automatically. No asset,
training,Path-1/protected CFR,GPU/evaluator/Slumbot/checkpoint/H19/later behavior or
official hands. L0.

The 2026-07-22 10:52 update below is historical.

Current authoritative update (2026-07-22 10:52 EDT): Phase FA Q001 launcher/runner/
auditor SHAs29a5e66ae0c58cebd217f7b4cf330c325dd23f4ec2967f824ff8ce375fb63a98 /
741e13fe6fcffef9b6a2ea681c46945834615afd7feee9163bf7a6cf03d6fc5b /
08f98f5057e399e08b95474e74a426af00145b196170ef936012f35606aa88f7;
implementation-audit SHA
a4c166aa4c16c015ed194d640c38ca17712ffa544c82fb570b0bb2da1d8c6368
PASS105/105 binds12/12 frozen inputs,exact runtime,compile/self-tests,runner23 gates,
auditor44 checks and exactly two fresh launcher-bound ContractProbe children. Both
exit0 with exact CPU/device/nonce/contract/runtime/runner identities,torch absent,
files_written0 and2963/2963 scoped snapshots diff0. Mapper accepts only exact
HUNLGameState plus one-to-one action-type/cent-amount slot identity and sum1 source
probabilities;projection/drop/collision/renormalization/illegal mass fail closed.
Bucket-only and legacy54dim rows remain unpromoted. MC32 is exact V5.5 4x8 with five
temperatures and8 CPU threads;quota shortfall is preserved as diagnostic NONPASS,no
cross-cell fill. No qualification/audit ran;qualification and20M roots absent,rows0.
Stop one-qualification-ready. A later transition may consume exactly one Q001 launch
through this launcher/audit SHA,then one launcher-owned audit and exact judgment. Do
not change code,run more probes,generate assets,train,touch Path-1/protected CFR,
launch GPU/evaluator/Slumbot/checkpoint/H19/later behavior or official hands. L0.

The 2026-07-22 10:30 update below is historical.

Current authoritative update (2026-07-22 10:30 EDT): Phase FA full teacher-asset design
preregistration/audit SHAs
74b7aeda43d46c1ec84ea72f58f3795c32279b548fdc7674f8fa837e99669a82 /
ee245f813fc9fd4a301f6a9dfc92761b4e3db51becf7de5361cd59aa8fb0ba68
PASS197/197 establish
`PHASE_FA_FULL_TEACHER_ASSET_DESIGN_REGISTERED_PREGENERATION_AUDIT_PASS_QUALIFICATION_READY_ONLY`.
The design freezes20M rows(16M@200bb,2M@100bb,2M@50bb),each depth equally across four
streets,eight line/raise-tree buckets and positions;400x50k gzip shards;eight separately
registered2.5M-row windows;8 CPU workers. CFR is native-depth primary only when exact
V5.5 state/action/probability mapping is one-to-one;projection/drop/collision/
renormalization fail closed. Fallback is qualification-gated MC32(4x8). Per-shard QA
requires hashes,exact quotas,512 spot replays and64 repeats;final PASS only permits a
separate Phase DW preregistration. Independent content-tree recomputation bound the
protected200bb/50bb/100bb sources;Path-1 remains terminal599/600 with1747 excluded and
legacy54dim/bucketed sources have no direct eligibility. No code,qualification,asset,
training or official hand ran;output root absent,L0. Next is separately registered Q001
implementation plus independent implementation audit only;do not implement or launch
automatically. No Path-1/protected mutation,GPU,trainer,evaluator,Slumbot,checkpoint,
H19/later arm or official hands.

Current authoritative update (2026-07-22 10:07 EDT): PCV019 is terminal
`PASS / PCV019_PASS_INVOCATION_ROBUST_EXACT_V55_INTERFACE_AND_BOUNDED_CPU_SMOKE`.
Exactly one registered smoke and one launcher-owned independent audit ran. Result/audit
SHAs c49f38fefa0aecd6cb08ee9aa6c2a296e0ed3c6ccdff3faad6fcc4327a898e3e /
30891e385e51740bb0b95cde66c982e75af1574dfbe1e50c63e4f8cd32644690
PASS23/23 and PASS44/44. The immutable five-file bundle has64 teacher rows(16/street),
48 terminal probes(16/class),31/31 inputs,wall0.2903830000432208s,RSS37.39453125MB,
bundle227682B,row-p950.0048059000400826335s,and batch-L1 mean/max
0.4581518791115685/0.7825096616549463. This proves only exact-V5.5 interface and bounded
CPU resource feasibility;training eligibility is FORBIDDEN,full-asset/behavior authority
NONE,official hands0,L0. Never rerun,extend,reclassify or mutate PCV019 output. Next is
separately registered reporting-and-design-only Phase FA full teacher-asset design
review fixing rows/parallelism,exact betting-line coverage,protected CFR teacher mapping,
>=32-rollout fallback,per-shard QA and immutable absolute outputs. Do not generate,
train,touch Path-1/protected assets,launch H19/later/GPU/evaluator/Slumbot/checkpoint or
official hands automatically.

Current authoritative update (2026-07-22 09:58 EDT): PCV019 launcher/runner/auditor
SHAs16f16fac0d421d3252ce16eb993f6c2eb210bf6a3221724d784eff0f616cd9bb /
ab63c3676742174ed80b664ebc7356ab0f34abf75edb093f6ed3151c562f3d9f /
4cb52a29a8300571650b0bf5c1bb28be460e5e7533861c6dc9305d4a7c887f67
and independent implementation-audit SHA
e4eecca09b78143eceefb84bfbd31e351d7584e6be3203bbb4f5bed450f137d7 PASS103/103.
The audit binds31/31 inputs,the exact runtime,compile/self-tests,science equivalence
16/16,runner23 gates,auditor44 gates and exactly two fresh launcher-bound ContractProbe
children;both exited0,observed the exact CPU-only device mode/nonce/contract/runtime/
runner hashes,torch absent,zero files,and2934/2934 scoped snapshots with diff0. No smoke
or result audit ran and the output root remains absent. Stop one-smoke-ready. On a later
authorized transition run exactly one bounded CPU smoke through the exact launcher and
immutable implementation-audit SHA,then the launcher-owned independent audit and exact
registered judgment without rerun. Do not change implementation,run more probes,
generate full assets,touch Path-1,launch H19/later arms,GPU,trainer,evaluator,Slumbot,
checkpoint or official hands. PCV018 remains terminal;L0.

Current authoritative update (2026-07-22 09:42 EDT): PCV019 preregistration/audit
SHAs9664243c6d0042c73935086e332afc63342cdfcc00ce8b3431400db92c5ae3f2 /
94644c8b6d6d855fe07d80b6bbac009efc970ba5ac4309c1cdfd793d1b7300b1 PASS149/149
establish
`PCV019_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_LAUNCH_READY_FOR_IMPLEMENTATION_ONLY`.
The registration freezes31/31 evidence inputs,PowerShell5.1/Python3.12.10,new seeds
2026072093/2026972093/2027972093,new absolute paths and device contract SHA
cee64165a651a0ca0ee99e2350859d567468c7b8e5ad9e70e01fce9253be6937.
Its sole nonbehavioral correction has two inseparable facets:every auditor CLI and
preregistered path is canonicalized with str(Path(value).resolve(strict=False)) before
equality,and launcher Audit mode owns hardcoded absolute arguments with no path override
and exact present-nonempty invocation marker. Every PCV018 science/scope/probability/
CPU/resource/classification gate is preserved;future independent result audit is44/44.
PCV018 stays terminal with no execution/code/output/seed/row/result reuse. Launcher,
runner,auditor,implementation audit and output root remain absent. Next is a separately
authorized implementation plus independent implementation audit with two fresh exact
ContractProbe children only;do not implement or launch automatically. No probe,smoke,
audit execution,full asset,Path-1 action,H19/later arm,GPU,trainer,evaluator,Slumbot,
checkpoint or official hands now. L0.

The 2026-07-22 09:31 update below is historical.

Current authoritative update (2026-07-22 09:31 EDT): DRIVE TO L5 v3 is active and
supersedes v2 and the PCV018 execution-window goal. Completion is only (A) one exact
frozen V5-lineage checkpoint with official greedy-direct Slumbot100k+ hands,bb/100>0,
95% CI lower>0 and complete hand-level evidence,or (B) frozen route-exhaustion
escalation after all four non-V6 hybrid legs are exhausted. Platform goal thread is
019f89fd-666d-7923-9bfc-1712eff5c791;activation SHA
bf29356f490af7c7cb57100a956727fbcae154a10640879298aed48df75bb4a1.
Route Review030 prereg/audit SHAs
172dde3ec21bbf94fcb720382350ee2dab4750d2ad3de0618f24d3a417a70641 /
fb109c51a4028275e6bcf5061c856373a6aa0151fd3793071c65cc37adee062d PASS72/72;
result/audit SHAs
58646cd83e97abcbd21a390916d716e00139dbf2b4ea23289406a0567d3a3b8f /
492cd65f5fee64a1a785d7cac2cf0dc919c7955df9a59cc3fb4a9bc559d0691b PASS82/82
select
`PCV019_NEW_TRAINERLESS_INVOCATION_ROBUST_EXACT_V55_DEVICE_INTERFACE_AND_BOUNDED_CPU_SMOKE`;
route_exhausted=false. PCV018 remains permanently terminal;preserve its runner PASS
science/device/resource evidence and terminal audit failure without repair,rerun,
reclassification or output mutation. PCV019 is a fresh registration with seeds
2026072093/2026972093/2027972093,new absolute paths,and every PCV018 gate preserved.
Its sole nonbehavioral invocation-robustness change requires both Path.resolve() on
every auditor path comparison and launcher-owned Audit mode with hardcoded absolute
paths and no operator path override. Next is separate PCV019 preregistration plus
independent preimplementation audit only. No PCV019 implementation/probe/smoke/audit
launch,full asset,Path-1 action,H19/later arm,GPU,trainer,evaluator,Slumbot,checkpoint
or official hands. L0.

The 2026-07-22 09:10 update below is historical.

Current authoritative update (2026-07-22 09:10 EDT): PCV018 is permanently terminal
`PCV018_FAIL_CLOSED_DEVICE_INTERFACE_OR_BOUNDED_CPU_SMOKE_GATE`. Implementation audit
SHA0e9e96512af3829ad0282c546b883c684a4b8d1e3d06b987905e201077b934a5 PASS42/42
binds15/15 inputs,the exact runtime and two fresh launcher-bound ContractProbe children;
both exited0,observed CUDA_VISIBLE_DEVICES=-1,the exact device mode/nonce/contract and
runtime/runner hashes,torch absent,and wrote zero files. The one registered smoke exited0
and its23/23 runner gates passed,but result/audit SHAs
d5cc12e86c97894f92defaaa753a132bf3b80560c63736c566970cc4ffdde495 /
3c9484ba79bdc897076044052fdbcc96064d86707c2d93d633555411974021e1 are terminal
FAIL_CLOSED because the independent auditor passed41/42 and failed only
`preregistered_outputs_exact`:the mandated relative `--root` string did not equal the
preregistered absolute output strings. Preserve the runner PASS result and audit failure
without repair,rerun,reclassification or output mutation. The archived draft1 checker-
defect audit remains provenance only. Next is separately registered Route Review030;
no automatic review,full asset,Path-1 action,H19/later arm,GPU,trainer,evaluator,
Slumbot,checkpoint or official hands. L0.

The 2026-07-20 00:59 update below is historical.

Current authoritative update (2026-07-20 00:59 EDT): PCV018 prereg/audit SHAs
951422e693e680a950b1d4395822a83e500fa0dbf8d7aad0979df9289fe60f6a /
bdc7a472a6a36c2b494b39dc7da1d058adcd86e3f3fd58656b149ee23fc34dd0
PASS76/76 establish
`PCV018_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_LAUNCH_READY_ONLY`. The sole frozen
correction is a Windows-safe parent-to-child CPU contract:CUDA_VISIBLE_DEVICES=-1,
PCV018_DEVICE_MODE=CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK,nonce2027972092,canonical
SHA921ed4befb30f3a910eae2894be150722138d9f4150511727deda0ca1f8a0e05.
Future implementation audit requires two fresh ContractProbe children through the same
launcher/runner boundary with exact values,torch absent,zero files and exit0. All15
inputs,Python binary,new paths,seeds2026072092/2026972092/2027972092,outputs and every
PCV017 science/resource/interpretation gate are frozen;PCV017 authority/code/output/
seed/result reuse is forbidden. Launcher,runner,auditor,implementation audit and output
root remain absent;no probe or smoke ran. Stop launch-ready:do not implement or launch
PCV018 automatically,generate full assets,touch Path-1,launch H19/later arms,trainer/
evaluator/Slumbot/GPU/checkpoint or official hands. L0.

The 2026-07-20 00:30 update below is historical.

Current authoritative update (2026-07-20 00:30 EDT): Route Review029 prereg/audit
SHAs92237f1fbe477440f51b8eb75e4fb356f1207a582ddcf1614bdbf3afadb8c14a /
c69cf89ec30e2717968530f31027f9cd0f4b235582100df0e082a7fbbd359c03
PASS45/45;result/audit SHAs
a4fe53686fe0b885a0620407ac3e3c6d055c004146a26219585f81108bc6dae6 /
88902e597fa27b38f043bbba37324118347f0399e6ffc72537384ac0c1222736
PASS68/68 select
`PCV018_NEW_TRAINERLESS_WINDOWS_SAFE_DEVICE_ADMISSION_AND_FRESH_EXACT_V55_BOUNDED_CPU_SMOKE`;
route_exhausted=false. PCV017 had zero output/rows/rollouts and exercised no exact-V5.5
interface or resource gate;its sole observed failure was the PowerShell parent-to-child
device-admission mismatch. PCV018 is a new registration,not a retry. It must separately
freeze/audit new code paths,seeds,output,the exact parent operation and child-observed
value,same-child-boundary validation,and CPU-only no-Torch/no-GPU/no-fallback admission,
while preserving every PCV017 science/resource/interpretation gate. Launch authority
NONE:do not implement/run PCV018,repair/rerun PCV017,generate full assets,touch Path-1,
launch H19/later arms,trainer/evaluator/Slumbot/GPU/checkpoint or official hands. L0.

The 2026-07-20 00:08 update below is historical.

Current authoritative update (2026-07-20 00:08 EDT): PCV017 is permanently terminal
`PCV017_FAIL_CLOSED_EXACT_V55_INTERFACE_OR_BOUNDED_CPU_SMOKE_GATE`. Prereg/audit SHAs
63249c1ab2a8fcd5d4b7701eae22f3177b48db48d648abc46ce21589460a7522 /
aa711438b6d92acdead4a0d1c4d0f1ac1b03a90eaea773a5ad51bed34e37d11d
PASS41/41;implementation audit SHA
2584da1da803fb611af1424802234db2570edd1c4818e7edd610bda99acbb471
was originally PASS55/55. Failure/audit SHAs
4eec401c023e86c432941da6e64b5c4ba62190d9c3c1cfd6e20d963a1b0cc6b9 /
22d5ef6c87c714803c98e5ca213c9cd2e3d14a015e45beca1fe261c40a0474c3
PASS37/37 bind the one attempt's pre-output device-admission failure:PowerShell removed
CUDA_VISIBLE_DEVICES on empty assignment,the child saw absent/None,and the runner exited1
with RuntimeError gpu_visibility_not_empty. Output root/results are absent and decision
rows/probes/rollouts are0. The implementation audit's execution authority is CENSUREd
for missing actual launcher semantics;preserve it and both scripts. Never rerun,repair,
extend,reclassify,reconstruct or infer interface/resource/method/behavior/strength from
PCV017. Next is separately registered and independently audited reporting-only Route
Review029. No automatic PCV018/H19/later arm,full asset,Path-1 action,GPU/trainer/
evaluator/Slumbot/checkpoint or official hands. L0.

The 2026-07-19 23:31 update below is historical.

Current authoritative update (2026-07-19 23:31 EDT): Route Review028 prereg/audit
SHAs cc84f01e2e9980d4f4ce684b9739c5494628510ccad77ea4171dcde8dda90b2a /
a9a9ed2913584472374ab01044b15f65c3208e80c7fd865f26bba55bbc898c2e
PASS36/36;result/audit SHAs
7dcde76c63070539ec08445bf9b0935c4d192852dd7b6f3064409d48d48356d8 /
f55b0e7de5a7ec09ab5986d21999ec9091ed0377d1756945172f4991343d5eef
PASS55/55 select
`PCV017_NEW_TRAINERLESS_EXACT_V55_TEACHER_SOLVER_INTERFACE_AND_BOUNDED_CPU_SMOKE`;
route_exhausted=false. PCV016 proves exact V5.5 semantic owners exist and localizes
G5-G8 to missing exact solver interface,full200 wiring,teacher exporter and transferable
CPU bound;it proves neither a complete alternative nor route infeasibility. PCV017 must
separately freeze/audit every source/output,replay/probability/full200/resource ceiling,
classification and abort before any implementation. Launch authority is NONE:do not
implement/run PCV017,generate full assets or training data,touch Path-1,launch H19/later
arms,trainer/evaluator/Slumbot/GPU/checkpoint or official hands. L0.

The 2026-07-19 23:10 update below is historical.

Current authoritative update (2026-07-19 23:10 EDT): PCV016 is permanently terminal
`PCV016_INCONCLUSIVE_EXACT_V55_TEACHER_INTERFACE_OR_RESOURCE_EVIDENCE_INSUFFICIENT`.
V1 prereg/audit SHAs a847bd33917e96fc8a1dfe778f85ce2375b6620a178c527e84bf9a099a3b1dd9 /
d16145b910341590be452df14e1d834f8e59b53ba0229acd2158ffed6f8cee15 were
CENSUREd before execution for omitting the Python Deep-CFR HUNL candidate;CENSURE SHA
6e8cb3b43e8f6dd676ec8792b17186eb97dc559d2d9536d89d1a825af95146a6.
Corrected v2 prereg/audit SHAs
b7a06d4e791d376b3aa7c1956ff6c2e70a9112bd3fef8fea18dafe7904b228f9 /
6aa65d2b8552bdd535dd4cbd18626073458fa85f3df2f57a3da43f77cbe18be1
PASS44/44;result/audit SHAs
b149e9f06715d102ac89a7f636f49dd1dde74f9756145dd3fcda95a27da7901f /
d391ce6dc5680b19f319b8dea889df505cb483b67f3c02e47782167ae56240ef
PASS64/64. Exact V5.5 semantic owners exist,but TypeScript Path-1 is separate postflop
SRP and Python Deep-CFR uses HUNLEncoder56,ordinal slots,no full200 training wiring or
exact exporter,and SRP50/CUDA defaults. No transferable exact-full-HUNL CPU resource
bound exists. Never rerun,reclassify or use PCV016 for method/behavior/strength
inference. Next is separately registered reporting-only Route Review028;do not launch
an asset design,H19/later arm or official hands automatically. Path-1 remains terminal
incomplete and untouched;L0.

The 2026-07-19 22:27 update below is historical.

Current authoritative update (2026-07-19 22:27 EDT): Route Review027 prereg/audit
SHAs4f2f7e7b10168651b1ce9a5dc4c5b4114d734f34b313b954fada4eb1e41ae0b4 /
084ff395c1edafd9063bd88835a11427d10c1ff1ede6112c2a49e1e5811f07f6
PASS33/33;result/audit SHAs
4f7129e8e7cd3378c7740495e55ad687046da5431338afb2e5801df065b396b6 /
7c8cd2ffa58fbe7e10c821ad81a021c0910ca30de8e05789fe7bd80804c31e74
PASS41/41 select
`PCV016_NEW_REPORTING_ONLY_EXACT_V55_TEACHER_SOLVER_FEASIBILITY_AND_ASSET_ROUTE_AUDIT`;
route_exhausted=false. PCV015 closes current Path-1 at599/600 with no action authority,
but H3-v3 separately identifies an untested exact-V5.5 transition/observation/
executable-9slot teacher route. PCV016 must separately freeze/audit a trainerless
read-only code/interface feasibility review. No code change or compile,process/GPU
launch,asset generation,Path-1 action,H19/trainer/evaluator/Slumbot/checkpoint or
official hands. PASS is feasibility-only and requires later separate asset registration;
L0.

The 2026-07-19 22:10 update below is historical.

Current authoritative update (2026-07-19 22:10 EDT): PCV015 is terminal
`PCV015_FAIL_CLOSED_PATH1_TERMINAL_INCOMPLETE_NO_RESTART`. Prereg/audit SHAs
b222d0e9dc5aa99b369d2e4a58e050fb6bc636d2a4b90855d271420b9c99ed1f /
72362297088eab76ffaec00b1b3072abf9b587a5d7439fd2d04f25a61a25bc00
PASS35/35;implementation audit SHA
f498b66d70406dfd4cb12c243b784af2078f6adcca9025c6522f4ca3bba843fe
PASS40/40;result/audit SHAs
cc8f1d5707b93a485ba158afd4f35974c79e2ee0ca4b97f96ae1ace6ec0a3418 /
002230447dacc67d58e01eaf4331834c27104eb4c938e74cda8b8cc55925135c
PASS37/37. Exact selection600;existing read-only gzip/meta/QA-valid pairs599. Board1747
is the sole missing pair and unresolved latest QA FAIL;solver status is
COMPLETED_WITH_QA_FAILURES,599/600,failed1. Registered coordinator PID23720 is absent.
Never restart,repair,replace,expand,write or signal Path-1. PCV015 is control-plane only
and gives no timing/method/behavior/strength authority. Next is separately registered
and independently audited reporting-only Route Review027. Do not launch H19 or later
automatically;no GPU workload,trainer,evaluator,checkpoint or official hands;L0.

The 2026-07-19 21:27 update below is historical.

Current authoritative update (2026-07-19 21:27 EDT): Route Review026 prereg/audit
SHAsfd16617eea700ee3ad6356f78246ab4d4608c03a800ae67c6af95949b52b0ee8 /
3ca352cfa2498f07eaecbb9b6f4b595fed0a0ef7bb4ee26dd9407a74bb18f883
PASS25/25;result/audit SHAs
a27011e2634526963e832cff7935b2cc9c1f116f7e08a80b296c0c3a057d1db6 /
c0ad83750c919c4fc315e6cca4c2f03576dacd5b2921f7ed65b183796a7337b2
PASS32/32 select
`PCV015_NEW_REPORTING_ONLY_PATH1_TERMINAL_LIFECYCLE_AND_ASSET_CLOSURE_AUDIT`;
route_exhausted=false. PCV014 observed only PID23720 absent;latest frozen Path-1
progress SHA d153cf5684cef59bb2aca0b62ffdb37d7a74cbf36bd54efa1f4aa111922aa2ed
is553/600,diagnostic-only and predates failure,so normal completion versus premature
loss remains unresolved. PCV015 must separately freeze/audit a trainerless read-only
selection/asset-pair/QA/illegal-row/error/lifecycle inspection. Exactly600 valid pairs
may support terminal-absent resource status;fewer than600 with coordinator absent fails
closed with no restart. No automatic PCV015/H19,Path-1 mutation or official hands;L0.

The 2026-07-19 21:03 update below is historical.

Current authoritative update (2026-07-19 21:03 EDT): PCV014 is permanently terminal
`PCV014_FAIL_CLOSED_PATH1_COORDINATOR_ABSENT_NO_RESULT`. Prereg/audit SHAs
8284a18e891409cc8adb9eea92eec9c6e78fc08c5285ec3b645d43865359e4c0 /
9409837dcd00655010769a516bdd4d4302c8f61e5b46b93bbf84694aced45b9e
PASS34/34;implementation audit SHA
76dc08e0dac0d509f4ced25c4835bbe2de5ae090be01b187d9f5d9de17f9f23c
PASS42/42;failure/audit SHAs
c0b8cc066e592df959e95e8b81438e841ea7aded41b1d26f77c858a408a20d32 /
317c22b40902ebe894e7a42ceb97be73cf6f6ee59438a2f40c210a6331f1ada2
PASS22/22. The initial resource snapshot raised psutil.NoSuchProcess for locked Path-1
PID23720 before conditioning:updates0,timed pairs0,result/raw bundle absent. Path-1 was
not inspected beyond the exception and was not modified/restarted/repaired. CENSURE the
helper exception preceding the result writer;never repair-in-place,rerun,reconstruct or
infer from PCV014. Next is separately registered/audited reporting-only Route Review026;
no automatic PCV015/H19,Path-1 mutation or official hands;L0.

The 2026-07-19 20:27 update below is historical.

Current authoritative update (2026-07-19 20:27 EDT): Route Review025 prereg/audit
SHAsbbc04c471430f2f91669247a145294a175dbb93286bf51cc3f103b9dfee55452 /
74786132e7a427b99e2ea1001cc089dc2495e81cf6bddb6f28ac1d52f58929db
PASS25/25;result/audit SHAs
8c35091207b69515d7cd40b76be90266e0a4819e4fb3abadb7ea14ac5523510e /
80c4f56eab670d5e587f4356858b55a0b59995968e63c8fef3ed92247dfcb714
PASS32/32 select
`PCV014_NEW_REPORTING_ONLY_WITHIN_CYCLE_INTERLEAVED_MATCHED_PAIR_GPU_TIMING`;
route_exhausted=false. PCV013 invalidated absolute admission as a feasible no-clock-
override control path before any timed block;PCV012 had recovered local stability with
residual cross-block association. This supports one new prospective variance-control
measurement,not timing cause. PCV014 must separately freeze/audit an exact preserved
source/workload/total-sample/CUDA-timer/telemetry/resource/threshold contract with only
adjacent order-balanced MSE/SmoothL1 matched-pair granularity changed. Do not launch
H19 automatically;no clock override,prior-row reuse,Path-1 mutation or official hands;
L0.

The 2026-07-19 20:04 update below is historical.

Current authoritative update (2026-07-19 20:04 EDT): PCV013 is permanently terminal
`PCV013_FAIL_CLOSED_ABSOLUTE_ADMISSION_NO_LATER_BLOCKS`. Prereg/audit SHAs
ca79c9219e605369ac188e4ece039bea7019be2c0e2dce1a6d32936d4b84fb19 /
36fab6db03ea62ea5b0ddf9d0458d07b3e43a357cf411bddaf90e0600c6597a2
PASS30/30;implementation audit SHA
6592e5a7bf4d463d94f3a205d6512517cb2ae11eb0ee5e3dd0878cdc031cfe76
PASS39/39;result/audit SHAs
afc79ede23e9d784f62630a433e16ab4ced3c56e11eddd6373ae7809a4cdf5e2 /
c0ef62e710934134922604e6fa78b8db06f294a9f38091f3f74a77a80eb94289
PASS23/23. Initial conditioning PASS after75.094s/141 balanced pairs;block0 local gate
PASS,but its absolute admission timed out after122.812s/43 balanced heat pairs with a
terminal4C temperature and300MHz SM-clock range. Zero timed blocks and no later block
ran. This is control-plane failure only and establishes no timing cause,method,behavior
or strength evidence. Never rerun,extend,reclassify or reconstruct PCV013. Next is
separately registered/audited reporting-only Route Review025;do not launch H19
automatically. Path-1 untouched;official hands0;L0.

The 2026-07-19 19:27 update below is historical.

Current authoritative update (2026-07-19 19:27 EDT): Route Review024 prereg/audit
SHAsc3ee82f9939360fe220eb783c866aca95848aa864647f03e268c20e40439de84 /
7575d01d27d3ba11abd6e8f4c3a562a85c991b8fff954d2f11a449aefec1318f
PASS22/22;result/audit SHAs
d9c6f1c60a7fd10ffb3971c55e183befd680291f94f12f8aaa4bfd23ff68eec8 /
fa3f24e3ffb1bcb8a3a1e91815b8156efc2c7cb197dfd1602d97e3a7af377b76
PASS28/28 select
`PCV013_NEW_REPORTING_ONLY_ABSOLUTE_CROSS_BLOCK_DEVICE_STATE_ALIGNED_TIMING`;
route_exhausted=false. PCV012 local envelopes recovered stability but did not align
absolute cross-block state;this remains association only. PCV013 must use new seeds
2026071989/2026971989/2027971989,new output,preserve PCV012's initial conditioning,
local gates,workload,order,timing,telemetry,resource contract and thresholds,and change
only one absolute block-start anchor derived prospectively from the new run with bounded
heat/idle admission. Separate immutable registration/implementation/audits must freeze
target derivation,tolerances,cadence,timeouts and aborts. No clock override,prior-row
reuse,H19,trainer,checkpoint,Path-1 mutation or official hands;L0.

The 2026-07-19 19:02 update below is historical.

Current authoritative update (2026-07-19 19:02 EDT): PCV012 is terminal
`PASS / PCV012_PASS_MEASUREMENT_COMPLETE_IN_BLOCK_DEVICE_EXCURSION_PERSISTS`.
Prereg/audit SHAs614887a88dce34e7236401738238b2b59e6c0b23e35979aa6f14368cee872aa0 /
6110a1ee54c99bec3f7ddccec56114bdf8beb686b1c95147a17faadab1e6586e
PASS27/27;implementation audit SHA
bcda32e7356890321aa383c1f7112f9a166afac1a7bf04b5d39f2b2aa57fb475
PASS32/32;result/audit SHAs
555bb7bc0039dd6d39cf54e38f8847adf171ccd1919e0f62726788ece35b3e68 /
59430171046c68fa9fc79d75e5859e991f2adeb39defcb32248eac4287e6d33d
PASS31/31. Initial conditioning and all eight block-local envelopes PASS;26 resource
snapshots PASS. MSE stability improved to0.966717>=0.95,but cross-block temperature
still ranged6C and order effects were MSE1.021241,SmoothL10.995372. This is mixed
control-plane association only,not cause or method/behavior/strength evidence. PCV012
is closed,no rerun/extension/reclassification/row reuse. Route Review024 required.
No H19,clock override,trainer,checkpoint,Path-1 mutation or official hands;L0.

The 2026-07-19 18:27 update below is historical.

Current authoritative update (2026-07-19 18:27 EDT): Route Review023 prereg/audit
SHAs02327be3d12126d8e2e61075d28a7199afc9d7b0547d988498036d57294910f8 /
415894fbe8e7b11bd59076dde229c96b4af4a17dbbfa7bb798b4007bd66ce0d4
PASS20/20;result/audit SHAs
90e487de4a5e7a49292ef8dd9a078f52a3861705018409c2ef118e0a3040ea57 /
eff8552b8f216b1b437bb4532a121c089e060f10dbff210b2d94f9304fced09c
PASS25/25 select `PCV012_NEW_REPORTING_ONLY_BLOCK_LOCAL_DEVICE_ENVELOPE_GATED_TIMING`;
route_exhausted=false. PCV011's premeasurement envelope passed but did not hold across
timed blocks;this remains association only. PCV012 must use new seeds
2026071988/2026971988/2027971988,new output,preserve PCV011's initial conditioning,
workload,order,timing,telemetry,resource contract and thresholds,and change only bounded
block-local device-envelope reestablishment before each timed block. Separate immutable
registration,implementation and audits must freeze every limit and abort. No clock
override,prior measurement-row reuse,H19,trainer,checkpoint,Path-1 mutation or official
hands;L0.

The 2026-07-19 18:04 update below is historical.

Current authoritative update (2026-07-19 18:04 EDT): PCV011 is terminal
`PASS / PCV011_PASS_MEASUREMENT_COMPLETE_IN_MEASUREMENT_DEVICE_EXCURSION_PERSISTS`.
Prereg/audit SHAs81e7f9b97422ec776ee63b540ac7cbda7948b2a23fc9504b733427524df9730b /
e7ca582115cc6c4d34205c263196358926d37d4b8105fc738ec92c63a6e50c87
PASS24/24;implementation audit SHA
04a4e9457f9fabd493f7822cc14369539c11edc32c3e769b10e7e1c5530fc74c
PASS28/28;result/audit SHAs
703bc7b83460ffc988748c8081377583a3b9d6ae237a465af99d36f2718e4f62 /
80bc3efbbe32fd66689dc5ca14ce3f2b4df85d596b9bffdb066921405744ca6c
PASS29/29. Conditioning passed after154.016s/242 balanced pairs with terminal
temperature/SM-clock/memory-clock/power ranges3C/0MHz/0MHz/8.27W,but measurement
temperature still ranged6C. MSE stability0.919775<0.95;order effects MSE1.025953,
SmoothL11.000513. These are control-plane associations only,not cause or method/
behavior/strength evidence. PCV011 is closed,no rerun/extension/reclassification.
Route Review023 required. No H19,clock override,trainer,checkpoint,Path-1 mutation or
official hands;L0.

The 2026-07-19 17:27 update below is historical.

Current authoritative update (2026-07-19 17:27 EDT): Route Review022 prereg/audit
SHAs789560392066527b6e8c2c21e91b7abffebb02283e9de4b40cc372a43262cbb7 /
3e82ea444001cda8b989cf95df795df80a4287f65a01e03bf0ee6abcbf1bf467
PASS19/19;result/audit SHAs
fd6447e423a1311454291eb010ef9df4e882484b61ea21b89438a4aea067380b /
6e110af8707fb5226dbcc1408e007c6bc63f681b0fba1ff3eeca5a2a3d46ba6f
PASS24/24 select
`PCV011_NEW_REPORTING_ONLY_THERMAL_STEADY_STATE_GPU_TIMING_REPLICATION`;
route_exhausted=false. PCV010's device excursion remains association,not cause. PCV011
must use new seeds2026071987/2026971987,new output,preserve the PCV010 source,full-PPO
workload,eight balanced blocks,CUDA-event timing,telemetry,phase-aware Path-1 contract
and thresholds,and change only bounded premeasurement thermal-steady-state conditioning
with a frozen fail-closed telemetry envelope. Separate immutable registration,
implementation and audits are required. No clock override,PCV010 rerun/data reuse,H19,
trainer,checkpoint,Path-1 mutation or official hands;L0.

The 2026-07-19 17:02 update below is historical.

Current authoritative update (2026-07-19 17:02 EDT): PCV010 is terminal
`PASS / PCV010_PASS_MEASUREMENT_COMPLETE_DEVICE_STATE_EXCURSION_OBSERVED`.
Prereg/audit SHAs34de730dc44775e88d7af408abd07d4f7096ffec53573ee28a5c3e70b0de3960 /
f423f3f1e8d9ee2c2f7675cc90a6536784a5b99519b77e14e75ac2b10dc12fa9
PASS20/20;implementation audit SHA
0e283299534b1badfdc9dcb284b8398cf9e9906e8ca3893f316a6e3e9c542677
PASS20/20;result/audit SHAs
b9fcd2921f53781d62f0c945738065c043a044eac9e4a881b22cdb2417b570de /
74c9c6db20376e352fa63322a973fd9d4480e4a057f46c7af790b8ee839e224c
PASS24/24. Eight balanced blocks and16 phase-aware snapshots PASS. Aggregate
MSE/SmoothL1 ratio0.998602;order-effect ratios1.000201/1.005585 are below the frozen1%
association threshold;MSE stability0.944302 is descriptive. Device-state excursion was
observed with temperature/SM-clock/power ranges16C/300MHz/66.16W. This is control-plane
association only,not a timing cause or method/behavior/strength evidence. PCV010 is
closed;PCV008 remains terminal without data. Next is separately registered/audited
Route Review022. No H19,trainer,checkpoint,Path-1 mutation or official hands;L0.

The 2026-07-19 16:28 update below is historical.

Current authoritative update (2026-07-19 16:28 EDT): Route Review021 prereg/audit
SHAs19ecf6d0636f30bf479f5d8c7111d50a58a8a5903b032e38b75edfba3692ca06 /
9e553c907292b9b0baf452a01fcf41bdd4b45ee1f8ae4a61f3cc05187ea1f4e3
PASS17/17;result/audit SHAs
f358094ffb149a0c49e233b6aa1fbe2ef8c087f497db828ce2c74107b12ccbde /
eef97df3ea9fbab506cf30d3d237c46d15aaa696445472a4e32c8ac1a7d8282f
PASS20/20 select
`PCV010_NEW_REPORTING_ONLY_ORDER_BALANCED_GPU_TIMING_WITH_PHASE_AWARE_PATH1_IDENTITY`;
route_exhausted=false. PCV010 must use new seeds2026071986/2026971986,new output,
preserve PCV008's eight-block CUDA-event/device-telemetry shape and change only the
resource predicate to PCV009's phase-aware contract at every block boundary. PCV008
stays terminal with no reconstructable/reusable data. PCV010 requires separate immutable
registration/implementation/audits and has not run. No trainer,checkpoint,H19,Path-1
mutation or official hands;current heartbeat stops after Route Review021,L0.

The 2026-07-19 16:01 update below is historical.

Current authoritative update (2026-07-19 16:01 EDT): PCV009 is terminal
`PASS / PCV009_PASS_PHASE_AWARE_PATH1_IDENTITY_CONTRACT`. Prereg/audit SHAs
a90b9566b76a7679070dcde2a664ac2e41335154ff7ee932d655af930771dc86 /
c5eeabd6cd507f48461319c14a44bece98ae10f66fef5af7585d195d94ba850d
PASS18/18;implementation audit SHA
42f8712147bbd3409dc438d69eb14608c5b472f5f15828936b0cf865ea679e5a
PASS18/18. Result/audit SHAs
76d6064dd64f06d0118e30f95689facaf6f6c63e63221e44a906deabf98f5852 /
aa24783ac67d71d407ac76ea6939e53c8d007a3151ab4ffa59cf0c350896a46e
PASS20/20 bind20 one-second snapshots:exact coordinator,six active solve roles,
unknown0,transient0,BelowNormal and GPU matches0. QA was not observed,but immutable
coordinator code binds its allowed phase transition. This validates only a prospective
resource contract;PCV008 remains terminal with no result. No timing/method/behavior/
strength inference,H19 or official hands. Route Review021 required;Path-1 untouched,L0.

The 2026-07-19 15:28 update below is historical.

Current authoritative update (2026-07-19 15:28 EDT): Route Review020 prereg/audit
SHAs79c498a0fa381df1174eea06151c7244f340ab4a7252ecdca8c9f49c3566b651 /
6cce032ef096988c906c66879166229d60fadfb2322eba57978040d504e50890
PASS16/16;result/audit SHAs
6a9443c9faedc948e284ca3c43d8573d1f7c0b79422bc6a52b1a53feba2a1dfc /
8034c2a94448a519c1f43d36a1320c8bbbeb9f9b804d2bb6b213930bfdc9b16a
PASS20/20 select `PCV009_REPORTING_ONLY_PHASE_AWARE_PATH1_IDENTITY_CONTRACT_AUDIT`;
route_exhausted=false. Coordinator code SHA71c60e... defines six logical loops that
fork a solve child,wait for exit,then spawn a QA child;the old checker SHA8191f4...
counts only solve-worker children. PCV008's five-solve-plus-one-QA snapshot is compatible
with a normal transition but cannot validate/reopen PCV008. PCV009 must be separately
registered,trainerless,CPU-only and read-only,allowlisting solve/QA roles while failing
on unknown roles,identity/priority/GPU changes. No Path-1 mutation,H19 or official hands;
current heartbeat stops after Route Review020,L0.

The 2026-07-19 15:03 update below is historical.

Current authoritative update (2026-07-19 15:03 EDT): PCV008 is terminal
`FAIL / PCV008_FAIL_CLOSED_PATH1_IDENTITY_CHANGED_NO_RESULT`. Prereg/audit SHAs
3df3d6c12e1b169cc08657d040d0407f03b1e3300754fe6396cb95a4d454dded /
832908cd2b7f6f83b794828409ed1b411591a07c0917adf55a7f8704cd67dde6
PASS18/18 and implementation audit SHA
bcfcf9dd8d123635ecd1dee8dd2e0ccf1cbdf6de12833286c0cae0a8ad649f11
PASS16/16 authorized one trainerless attempt. After eight fixed GPU blocks,the final
resource gate observed five Path-1 solve workers instead of frozen six and raised before
result write;PID23720 remained BelowNormal with a qa-200bb-board child. The agent did
not touch Path-1. Execution-failure/terminal-audit SHAs
c53014f03da6b11d5b3fe0f7705dfcf4fbcd56578c51e0ffda742ab31502b78f /
a50679421f7d0cd71facf17463579d1e5c7503dbc618689f14c5c6738b49ff37
PASS18/18 bind no immutable result/raw bundle. Timing attribution,console reconstruction,
rerun,reclassification and inference are forbidden. No trainer,checkpoint,H19,evaluator,
Slumbot or official hand. Route Review020 required;current heartbeat stops here,L0.

The 2026-07-19 14:27 update below is historical.

Current authoritative update (2026-07-19 14:27 EDT): Route Review019 prereg/audit
SHAs81183ed99401a6e41735ebf1090611781fefd9dcb03e6ce16227c634afeaed73 /
55b6b56d31ce848e2678fa3ccb75bc1a324e26e4b3920a9ddc8067d7b6da9176
PASS16/16;result/audit SHAs
2581f9a6566a366b99884a9a49373e02e725efe30ab5b36ddc486dced0ba7855 /
6c7d7fc4dadd505391d16a51b4f85d589001138db7cd2e344ff770a78eed0e19
PASS20/20 select `PCV008_REPORTING_ONLY_ORDER_BALANCED_GPU_TIMING_JITTER_ATTRIBUTION`;
route_exhausted=false. H18 had zero arm exposure,passed corrected equivalence and
throughput,but stability0.9497993243 failed while PCV007 passed the same threshold at
0.952729. This supports only a separately preregistered trainerless timing-attribution
prerequisite;H18 rerun,reclassification,method inference,threshold relaxation and
direct H19 launch remain forbidden. PCV008 may prospectively measure order-balanced
torch.cuda.Event timing and device state only;no trainer,checkpoint,behavior or official
hands. Current heartbeat stops after Route Review019. Path-1 PID23720/six BelowNormal
workers untouched;official hands0,L0.

The 2026-07-19 14:14 update below is historical.

Current authoritative update (2026-07-19 14:14 EDT): H18 is permanently terminal
`FAIL / H18_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_GATE_NO_LAUNCH`. Prereg/audit SHAs
8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481 /
b1e9b050a5f31ea55fa33b0aa68872bdbd3730f674564455b1b5c5f870ed8f14
PASS32/32;implementation/integration PASS23/23 and PASS31/31. Immutable design-lock /
audit SHAs0dbae21f4008d138ac84b3465fa5b50673026958fa93c46802947c3e98083e73 /
9436f24a0809710a1d74fdb1341ea7d8f56b8a549a1253a178dbacac0dde3acb
PASS73/73 and preflight SHAa860b65edb49843a63ab740bd8f9fd8b98f1b35dad5600d7c7f97ee1dc361780
PASS. Reporting-only calibration/audit SHAs
a869996f4ad94857320dae2d20f9efbcc6cd6721c7f77e61dbe8482ee3550977 /
3e019d3eed71a0e7317c800bba55d6fc4d0f3fea0f396c1aa90595031cf19d86
bind throughput1.020266 and corrected tolerance gates PASS,but MSE repeat stability
0.9497993243<0.95 FAIL_CLOSED. Judgment/terminal-audit SHAs
e97c35dcdaf6497b1885286e36814e13209d0341aaff5b53697760fac2a6d111 /
9aaeb6a402a4936c7065e26ddbd43a4ab930a69e19617979771d63f429071507
PASS28/28 confirm no sentinel,arm,trainer,checkpoint,evaluator or official hand. Never
rerun,resume,extend,reclassify or infer from H18. Route Review019 is required before
any later window;current heartbeat stops at this fail-closed prerequisite and no H19
arm is authorized. Path-1 PID23720/six BelowNormal workers untouched;official hands0,L0.

The 2026-07-19 13:29 update below is historical.

Current authoritative update (2026-07-19 13:29 EDT): PCV007 is terminal
`PASS / PCV007_PASS_NUMERICAL_ENVELOPE_AND_GPU_EVENT_TIMING`;result/audit SHAs
df785e28f1424906630edb90af4853a66b97d320f94a1d22aef465757e21aabc /
8cac33b378d93f0bdd79a5456c3a115326558899b39bb6671d88bd8677b57766
PASS19/19. Cross-mode non-value model/optimizer maxima1.490116e-8 /1.164153e-10
are below frozen1e-6 /1e-8 tolerances and within same-mode CUDA envelopes;CUDA-event
throughput0.999960 and MSE stability0.952729 pass. This is control-plane evidence only.
Route Review018 prereg/audit SHAs
9ad2a539895adbb309b39172f2d33471c84c7a697103868134bac8f9938c89ff /
bbc2f89ce5ec6c97e4fde57bfa2d45bb7017aa35f5c682b6a49f4c58781393eb
PASS12/12;result/audit SHAs
21a5dfaefc7021b60c65b5c558a0d4be83940d2f6b90b1379c31a592ffba7a23 /
14980792130339d1ca2f8f71870bddeb539f85a6781c4ab1bfaf62f4dcae9f51
PASS17/17 select separately registered H18 prearm correction preparation;
route_exhausted=false. H18 must preserve exact clean H11 source,fresh fixed20M
same-start arms and MSE-versus-SmoothL1-beta1 as the sole scientific variable;only
tolerance-bound non-value equivalence and frozen CUDA-event timing may change in the
prearm control plane. Current heartbeat forbids automatic H18 arm launch. H16,H17,
Huber and all terminal partials remain closed. Path-1 PID23720/six BelowNormal CPU
workers untouched;official hands0,L0.

The 2026-07-19 13:16 update below is historical.

Current authoritative update (2026-07-19 13:16 EDT): H17 is permanently terminal
`FAIL / H17_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_GATE_NO_LAUNCH`;judgment/terminal-audit
SHAs2adcda7fa166f997f621827dd51a6475adba80d16282cd4e839805bc43156927 /
bdf67c41316344ba3309ad12390b47cf7519688fee639d94f64ad96266678a8b
PASS22/22 bind no arm,sentinel,trainer,checkpoint,evaluator or official hand. Never
rerun,resume,extend,reclassify or infer method/strength. PCV006 terminal result/audit
SHAsd99f6ee51484bdd9c4d3637f8931dc0b9a06124167f1d2f36adc09eec8d6cd81 /
3f8de7d8193db346d53a44350c123cb1edd519915dae58ef083de00a664fa7cd
PASS13/13 localize one non-value model delta(max2.98e-8) and four optimizer deltas
(max1.63e-10),without proving cause. Route Review017 result/audit SHAs
46d1e1bb84912f9c12b63d4dd326875ce7a03f180a6f08e08c4696ad6d6859e2 /
85ac7bcab8480a3676cbe7eb129f863bc498a53911105af1594a921f2d61ba2d
select trainerless PCV007;route_exhausted=false. PCV007 prereg/audit SHAs
71b6962793b26db3ea852ff4bff7424c7688dd800a3c6f70306aef2310a20c7d /
cb476afad390a2ad9005e3f414a72fccd77753f9fef3846359d5d5b16e8c2ef9
PASS14/14 freeze same-mode numerical envelopes and GPU-event timing. Next is PCV007
execution;no H18/behavior launch authority. Path-1 PID23720/six BelowNormal workers
untouched;official hands0,L0.

The 2026-07-19 13:04 update below is historical.

Current authoritative update (2026-07-19 13:04 EDT): H16 is permanently terminal
`FAIL / H16_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_EXECUTION_NO_LAUNCH`;judgment/audit
SHAs96e0a4bea8c119c991ad1cd2710e7897d7938a161451e7cf7fec65400a8c86d0 /
3076c88f1e136cec92a15455cda19ff7241d882f62f65cf9b504c2c369b13ec9
PASS22/22 bind no arm,sentinel,trainer,evaluator or official hand. Never rerun,resume,
extend,reclassify or infer method/strength from H16. PCV005 is also terminal FAIL:
result/audit SHAs5da012bda5738542488d22e0ed4a1245f4b1cfb907cb7f1a6c5e408f88785858 /
38fb16beda8c877422c69023c1aaf4c5c37caf592d2dd6058738a03d68d9c11e
PASS11/11;Huber/SmoothL1 ratio0.9948549347<1.0,so Huber is rejected,while trigger24/24,
equivalence,original SmoothL1/MSE1.00865 and MSE stability0.95571 are valid supporting
components. Route Review015 result/audit SHAs
562280fa5398006998ddcd907ae81c802308ab75432f2a6a62ec4aabd9ffa4bb /
022a2e62cb061ca57246498b79efc73ee49a8677171e5b4461c0d7576c85f5f3 PASS6/6
select H17;route_exhausted=false. H17 preregistration/audit SHAs
df256560d69928c9f70e6df5457c1575cc81124ba80f34f9b15261293cefe7fc /
e002f2a93f3598c59e1507eb6992038ee282886576747415e8d490934c82925b
PASS25/25 freeze exact clean H11 source,fresh fixed20M arms,original MSE-versus-
SmoothL1-beta1 science and corrected offset10 deterministic per-arm calibration.
Implementation/integration audit SHAs
3a8fbfb972e18fda87bf9fc61f499846ca9e24657a168c78642675193ff8071e /
4904cbd8097850dd6490947db60d1c8329c73dffd3def3f07f44dbc5e76417b4
PASS23/23 and PASS31/31;tests36/36. Design-lock/audit SHAs
d82e6d8da6cd787e7f972e295344396ce35ad3828963fbfa9472548e5f9e3c7e /
22ea9eb1a1d00f9f13233dba06c2176c26e4b9606bee3d47d106e2594bafba44
PASS67/67. Preflight SHA9e30127b9138247971be29aab8ac6d8efd2aa83e3bb0f3e5c00bdf5d2c352967
is PASS_READY_H17_CONTROL_LAUNCH;launcher ValidateOnly PASS. Next is one exact control
launch;offset10 calibration must PASS before sentinel/trainer. Once active,no observer
command is permitted. Huber and terminal partials remain forbidden. Path-1 PID23720/six
BelowNormal CPU workers untouched;official hands0,L0.

The 2026-07-19 12:16 update below is historical.

Current authoritative update (2026-07-19 12:03 EDT): H14 is permanently terminal
`INCONCLUSIVE / H14_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`;its180,772-hand
control partial at iter35062 /576,202,673 is forbidden. Terminal audit SHA
00e7dd6f1057911d9dc95b12080e1d6df205cb86c1f054896ee85f93d873e05b PASS43/43.
CPV003 remains terminal FAIL_CLOSED. Route Review012 selected CPV004;CPV004 result/
audit SHAs69cdeedc406d5322a407cf3abd54d5f10d13d50ade87c84448b2a49dca132449 /
b4b03759131ddfc71e04842459fafc3ea46ee684cd6de430a1c6f610cdee38cf
PASS and route_exhausted=false. H15 prereg/audit SHAs
5631c27c29f1379ea16c5b246dccc312e830a2e50d5335dfac531798c882582c /
ae8a3563313f97b3098faf199ee752a8d65b41d5f95addf8a81e839c006cb6a3
PASS47/47;implementation PASS23/23 and integration audit-v5 SHA
b7571ed2a792dcf8fea188a8880afc0a8db15db37572ae0b880a7c105a292f4e PASS27/27.
Prelaunch lock v1/v2 are preserved superseded after fail-closed mirror-alias and Windows
CIM slash defects. Authoritative H15 lock-v3/audit SHAs
e97848d36fd6e28a1d77b4add05f524ea68655452bddb612be0703d7c0a112e4 /
8e319fa0fb3ee323e47f9ca32d6d0ad77855199d976ead4763f11cc3a77ca86c
PASS71/71;full suite39/39. Live preflight SHA
5f9962333cae6c693576997e32620d42da540287d134f9743f7228c380bc8fce is
PASS_READY_H15_CONTROL_LAUNCH;canonical rearm and control launcher ValidateOnly PASS.
Next is exact control production PERF-CAL then sentinel/trainer/ordered rearm. Once
active,no observer command may run. Path-1 PID23720/six BelowNormal workers remains
untouched;official hands0,latest strength L0.

The 2026-07-17 12:45 update below is historical.

Current authoritative update (2026-07-17 12:45 EDT): H13 is permanently terminal
`INCONCLUSIVE / H13_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION` at zero progress;
incident/judgment/terminal-audit SHAs cad2d325faad44b12604f7b8d930408dc80716cf10aaa2c1c30430b80346172d /
b0cc56f55f985819d748989ca1c0574ae8b176495dfcab064aae659de60b8ce6 /
e061add072023f8a474780fe6300bea12988d18d7f0150c0d334086b564a9fb5,
audit PASS34/34. Never resume,reclassify,evaluate or infer from H13. Route Review010
result/audit SHAs1c4ad93ce51350bb38374a81d7c1f5d53c70ea1f9f3b7400933f434f7268b3a7 /
401e7f5044b32d1d545317bde1e49eeadf611e505374e40f7c04b3175c96aac6
PASS45/45 select fresh H14;route_exhausted=false. H14 prereg/audit PASS46/46;
prospective exact lifecycle-child repair audits pass and full suite39/39 PASS.
Immutable H14 lock-v6/audit SHAs229763f9a432026c2dbcae3259fec9448e773d670f4036a940a1ba16a86b3694 /
f2e5bab910e45dbe543467d7fd85f8c9d07539a6c6e3ee6d44324dcf2033501f
PASS. Live preflight SHA11ff6fbd94a8036f5b0230014c32ef0efde6025377bd82fa8ac9973e9326885b
is PASS_READY_H14_CONTROL_LAUNCH and launcher ValidateOnly PASS. Next is one exact
control launcher with production PERF-CAL then sentinel/trainer/ordered rearm. Once
active,no parent/delegated observer command may run. Path-1 PID23720/six BelowNormal
CPU workers may continue;official hands0,latest official strength L0.

The 2026-07-16 17:04 update below is historical.

Current authoritative update (2026-07-16 17:04 EDT): CAL-EXT-002 is terminal
FAIL_CLOSED on exact H11 control iter35051 /576,021,901,SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13:
5,000 official greedy-direct hands,-146.1726 bb/100,CI[-238.5979,-53.7473],L0.
Completion/audit SHAs89baf334e35cf699b75f0845a3c1dea70335ddbe4ee81e219a15048dc4e9b9d7 /
e5dc2487ce8c0e4d0712a79c3b1bde6f41d488ed857ad1504068a5cd0aafaba3
PASS52/52. Unexpected played/greedy postflop-aggression failures block promotion and
formal100k;loss evidence is observational and cannot authorize action tuning. Route
Review009 result/audit SHAs0934e77fc7763f766d6ed344d7af9481c8a69bc728d287acf1821a1dde34c92f /
adcf6804692f21f72221c9cb21ab7009e64c534607bc005d0c95d74b196f2656
PASS44/44 select gated H13,route_exhausted=false. Prospective control-plane repair/audit
SHAse10cbfa805f93b1a61bf20a338bcb64b20b28caa95b812d60044cbb29bc40901 /
8a4bb96b0378a5d74bd690ddf63859755d907e277825d29b5fa41bd719e61078
PASS25/25 after48/48 tests. Next is immutable H13 preregistration and full prelaunch;
launch authority NONE. H12 stays terminal;Path-1 PID37656/six workers untouched.

The 2026-07-16 15:54 H12-terminal update below is historical.

Current authoritative update (2026-07-16 15:54 EDT): H12 is permanently terminal
`INCONCLUSIVE / H12_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`. Incident SHA
7569a5121face4fe445f6fd1227c98906340cc71b1f08fde30aae1cca6ad2433,judgment SHA
fbb927b2c37365325c4a72c4bce71e595d9bf2f66dfffa4edcd646d2f568d6dc and terminal
audit SHA3eca05fd8c73227f143ea495e94df66d08f31668f6fd98b26482ec422d448eb3
PASS33/33 bind exact control progress0 hands at source iter35051 /576,021,901.
Trainer stopped;no endpoint,treatment,mirror,evaluation or official hand exists. Never
resume,extend,reclassify,repair-in-place,evaluate or infer from H12. The health watcher
failed on an absent startup log and the protocol watcher misclassified the exact ordered-
rearm supervisor,which terminated trainer29392. Production PERF-CAL is supporting-only.
Next is separately locked CAL-EXT-002 on exact clean H11 control checkpoint SHA
96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,
greedy-direct4x1,250,no adaptive extension,full bundle,then Route Review009. Latest
official strength L0;Path-1 PID37656/six BelowNormal CPU workers remains untouched.

The 2026-07-16 15:46 H12-ready update below is historical and has no authority.

Current authoritative update (2026-07-16 15:46 EDT): H12 preregistration v3 SHA
7ecd7a4342f75a92f4d4f12493bcd5fda9e3e92e7f43f023f8779becbdb48e57 and audit SHA
8d4f6239e94a80d92da2441deef39d1d59612dd1b5e951bba018592e7d207850 PASS42/42
supersede v1/v2 before any trainer with source,arms,science,gates and interpretation
unchanged. Implementation audit v4 SHAf52f95e7c28d2958380eb24cb69a16c455a4b3b6a8e60a4523c621a652494ca6
PASS21/21;focused/regression suite44/44 PASS. Design-lock v2 SHA
a5318450b699bb2c9b0d6385fc386829155409db68029f47da0121e5ef766c39 plus audit SHA
e44c47e008cfb4ccb85d0e0222b77e0f8cdefed4a557fe8e99d1f641f114ebf3 PASS.
Both ordered rearm ValidateOnly gates PASS. Live preflight SHA
1da5bed02e1cde812041160fc7276d597f6eb12406f8d363b6f83d04d654d807 is
PASS_READY_H12_CONTROL_LAUNCH and exact launcher ValidateOnly is ready. Next is one
exact control launch:production PERF-CAL10/40/3 must PASS before sentinel/trainer,
then canonical ordered rearm. Once active,no parent/delegated observer command may
run. Path-1 PID37656/six BelowNormal CPU workers remains untouched;official hands0.

The 2026-07-16 15:30 H12-registered update below is historical.

Current authoritative update (2026-07-16 15:30 EDT): H12 is exactly
`REGISTERED_NO_LAUNCH`. Preregistration SHA
a5939812215e42e924566f1eef20d869bbc8a0d64a8960aa25242e7917e1656c and independent
audit SHA c394666b9c0508d39d759fbe507b879b34d3c39d8b607a320485a95bb7384971
PASS40/40 freeze exact H11-control source iter35051 /576,021,901,SHA
96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,fresh fixed20M
same-start arms,and catch-up MSE versus SmoothL1 beta1 only with every H11 scientific
gate unchanged. Offline PERF-CAL smoke/audit PASS19/19 at ratio1.079284>=0.95 is
readiness-only;exact pre-arm10/40/3 calibration and treatment common-MSE match>=0.95
remain mandatory. Exact H12 health producer plus dependency-ordered rearm are
implemented and tests31/31 PASS. Launch authority remains NONE pending child lifecycle
implementation/audit,design lock,preflight,exact control PERF-CAL and canonical rearm.
No trainer/evaluator/mirror/Slumbot;official hands0. Path-1 PID37656/six BelowNormal
CPU workers remains untouched. CAL-EXT-002 is mandatory after H12 before H13 unless
exact H12 PASS quick5k satisfies it.

The 2026-07-16 15:10 H11-terminal update below is historical context.

Current authoritative update (2026-07-16 15:10 EDT): H11 is permanently terminal
`FAIL / H11_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`. Judgment SHA
88f86867183a36abbf34fedc6eb7556b2fd81e33c1fd47f79e44031ae41fa316 binds
control1971.341469h/s,treatment1366.486603h/s,ratio0.6931760047<0.85;watcher
terminated treatment at iter33895 /557,014,309. Treatment endpoint,mirror and official
hands are absent. Terminal audit SHA
fb6217793ea703eb7521dcc6b7d9bdf2d4980c5895c578867e5208aa117c0122 PASS30/30.
Never resume,extend,reclassify or use the treatment partial. Reporting diagnosis SHA
8e92b23f9d2984b1cbc2f83bf797f1a5962476e558064ebcda2c3b4d5261c6bd preserves
the protocol FAIL but permits no SmoothL1 method inference. Route Review008 result SHA
f118c73e4721a2c06731798aaf63fc4762dd63d513c97fa5fa6674f959a1bffe and audit SHA
042f5247367e17e5656d6be4334cf12d47ea7a907233d076765a80088935832e PASS47/47,
route_exhausted=false,select resource-matched H12 from exact clean H11 control
iter35051 /576,021,901,checkpoint SHA
96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13. H12 launch
authority NONE until audited PERF-CAL ratios>=0.95,canonical endpoint-health producer,
dependency-ordered rearm,new preregistration/implementation/lock/preflight/rearm all
PASS. External debt20,010,816;CAL-EXT-002 required after H12 before H13. Path-1
PID37656/six BelowNormal workers remains untouched;official strength L0.

The 2026-07-16 07:49 H11-control-recovery update below is historical.

Current authoritative update (2026-07-16 07:49 EDT): H11 control
`v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715` finished cleanly at
iter35051 /576,021,901 hands,overshoot10,816<=50,000,stderr0,protocol
ARM_FINISHED_GUARDS_PASS,resource violations0,provenance PASS1217 and first60
1971.341469h/s. Treatment does not exist;official hands0. The endpoint watcher timed
out because strict H11 rearm blocked the generic health producer while the endpoint
contract still required exact health. Original failure/downstream blocked artifacts
are preserved. Reporting-only recovery SHA
58f169f8a620e588f86e55ad35c6090c2ef31390f841d6babf2d5af5084c4c32 published exact
health PASS14/14 without checkpoint,behavior,gate or verdict change;independent audit
PASS29/29 SHAcfb3a8a204e788ec03b3a69910a1a0ef625ebcd9ee685eee4618badd46daf4dd.
The correction is append-only CENSUREd. Next is canonical rearm:the unchanged locked
endpoint watcher must PASS before exact treatment launch. Once treatment starts,no
parent/delegated observer command may run;mirror/evaluator/Slumbot remain blocked.

The 2026-07-15 04:14 H11-ready update below is historical.

Current authoritative update (2026-07-16 17:19 EDT): H13 is locked and ready for its
one exact control launch. Preregistration/audit SHAs
0b13e2a424d498f736d257097acaa412baba1449437f99c9ddbba9cf3cf5e341 /
05ade0eb88cdb397965f819b512e1da9a9334c867ca05c694df7a965fb175042
PASS42/42. Implementation audit-v2 SHA
1396817f1dee35257383e19fca922987fb8c212e3a261721040066b4f33461f7
PASS21/21 and focused suite37/37. Immutable design-lock v2 SHA
c65f998f32d10ee8f0b105abe684723dfcacedaa9de39b149c1efcfbde5ec1c4
and audit SHAbc02103dfe5ea81975d4a7fa376a4c22f9d9a742101e2b8a83dae460aa9f5b0f
PASS. Live preflight SHA867ee60cb6c7ef0fac04b4f4387c8fb3864b7685feeb5751d2404fc94c26272f
is PASS_READY_H13_CONTROL_LAUNCH;canonical classification and control launcher
ValidateOnly PASS. Exact source is H11 control iter35051 /576,021,901,SHA96a007...;
fresh fixed20M arms change catch-up MSE to SmoothL1 beta1 only. Next is exact locked
control launcher with production PERF-CAL then sentinel/trainer/ordered rearm. Once
active,no parent/delegated observer command is allowed. Official hands0;Path-1 remains
PID37656 with six BelowNormal workers. The H11 update below is historical.

Current authoritative update (2026-07-15 04:14 EDT): H11 implementation audit v2
SHA659ef9b5bdc209a0c923106e958f1537fbc1810876ffc1bd142cb73511987793 PASS18/18
and focused suite15/15 PASS. Immutable design lock SHA
d6c5019439ff6ee1543dc6a9a61b7214f4d0a283b2847096ed6074c2366616d8 plus audit PASS.
Live preflight is PASS_READY_H11_CONTROL_LAUNCH:canonical H8 source/optimizer,all
hashes,absent H11 dirs,no trainer/evaluator,prior terminal sentinel,and Path-1 PID37656
with six BelowNormal workers pass. Canonical strict rearm and control launcher
ValidateOnly PASS. Next is one exact locked control launch. Once active,run no parent/
delegated shell,file-read,hash,process-list or other observer command;only locked H11
lifecycle and unchanged Path-1 may remain. Official hands0.

The 03:54 H11-registered update below is historical.

Current authoritative update (2026-07-15 03:54 EDT): Route Review007 result SHA
e53d7e72a53317ce88501d12c877f96d4c1dc2ec7edcd497c786ef7524403c93 and audit
SHAe24338f58f8eb434aefa406f81fcc3aed5146226c35d4fb9de5bc876b2165ff9 PASS36/36
select a new clean H11 after a mandatory control-plane gate;route_exhausted=false.
H11 preregistration SHAd493b1f9e936d89f0c2e51a0b6c5dbc5a8dd20b312d5f9cd5e415f43f44528d0
and audit SHA7f1aa18b396facd3a8148f6ce1e87f01653b1532959de0733cb9c27087e07852
PASS25/25 freeze canonical H8 source,fresh fixed20M arms,MSE versus SmoothL1 beta1.0
only,and unchanged H10 scientific gates. H9/H10 partials and H10 first60 reuse are
forbidden. H11 status REGISTERED_NO_LAUNCH:full trigger provenance,either-arm abort
terminalization,zero parent/delegated observer commands,implementation audit,design
lock,preflight and canonical rearm must all PASS first. Official hands0;no trainer,
evaluator,mirror or Slumbot launch authority. Path-1 remains unchanged.

The H10-terminal update immediately below remains terminal incident history.

Current authoritative update (2026-07-15 03:46 EDT): H10 is permanently terminal
`INCONCLUSIVE / H10_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`. Judgment SHA
c29671f5e5fce292d0fdadc4a351c2c089137f2d018f614b7564657dd3178897 and incident
SHA5c40cb7b692d71f8211bacf05aba4cc1571f8e0bd4ab34d140a40a421e5adb57 bind
control iter33912 /557,293,500,18,717,585 hands before target;treatment never launched,
official hands0. First60 PASS1779.760034h/s is throughput-only. Watcher PID evidence
stored only PID7848/token and cannot prove contention;the frozen matcher is overbroad
enough to catch goal-v2-permitted read-only CardPilot PowerShell observers. The verdict
still stands because the watcher terminated trainer46712. Never resume,extend,evaluate
or launch H10 treatment. Sentinel is terminal INCONCLUSIVE;no trainer/evaluator/mirror/
Slumbot remains. Next is separately registered Route Review007 and fail-closed process-
provenance correction before any new arm;launch authority NONE. Path-1 remains unchanged.

The 03:26 H10-control-active update immediately below is historical.

Current authoritative update (2026-07-15 03:26 EDT): H10 fresh control
`v5_hybrid_h10_control_catchmse_same33834_20m_r1_20260715` is active as PID46712
from exact canonical H8 source under design-lock SHA
a0f959f882846eb0d1454aaa9627366f7eaa8b123baa3e1febdbae2145221905.
Latest observed manifest iter33843 /556,158,901,target576,011,085;optimizer preserved,
catch-up MSE,target-KL0.03. Sentinel is H10_CONTROL_ACTIVE;canonical rearm survival
PASS with endpoint48728,protocol46248,treatment-launch49060 and completion29100.
Protocol ARM_RUNNING_GUARDS_PASS,isolation violations0,first60 pending,official hands0.
While sentinel is active,run no non-H10 project process;generic/Slumbot/mirror/
calibration paths are blocked. Exact watchers autonomously freeze control and launch
treatment only after registered PASS.

Prior authoritative update (2026-07-15 03:22 EDT): post-CAL H10 is locked and ready
for exact control launch. Implementation audit v2 SHA
581f3879c52451e38c86d610349395fda61544d670788b0cf158424d43b02da8 PASSes
all14 checks;focused tests24/24 PASS. Design lock SHA
a0f959f882846eb0d1454aaa9627366f7eaa8b123baa3e1febdbae2145221905 and audit SHA
1a78ea584e4775d1333320d8718568dfe0972969b99be3c7f0a9ab989078b68a PASS.
Preflight SHA4443e900a3c9c7624804df1539dfec9130c949e3fba4498c40ac1432e1719b5c
is PASS_READY_H10_CONTROL_LAUNCH;canonical rearm and launcher ValidateOnly PASS.
Next is the exact locked control launcher,which must create the active-window sentinel
before trainer start and pass manifest plus canonical-rearm survival. During H10 only
exact locked H10 lifecycle processes and the unchanged Path-1 job are allowed;no
Slumbot/mirror/calibration/generic project scripts and official hands0. H9 partial and
CAL benchmark-copy paths remain forbidden sources.

Prior authoritative update (2026-07-15): CAL-EXT-001 is terminal complete on the
exact H8 endpoint:5,000 official greedy-direct hands,-207.1804 bb/100,95% CI
[-297.6644,-116.6964],L0,full bundle PASS. Completion SHA
04eb29d61f73031d943ee6dc098f596c145515d8faf17ae30255259abe693019 and audit SHA
098a5e5946ecad263cd6a42fb6a62c09849aa457d046526a82125050f37a9679 are
authoritative. This pays external debt but is calibration-only and authorizes no
promotion or strength claim. Post-CAL Route Review006 result SHA
6420251b4e1ab8c54f8935dc375beea04c2038e3a8e2a69f432111a091e49bfe selects a
new clean H10 and says route_exhausted=false. New H10 preregistration SHA
cf562528360e05e4683bc3bd04edc19ba49ea98c2a2ddeb4d92f45805eab11fc is
REGISTERED_NO_LAUNCH: fresh20260715 same-start fixed20M arms from canonical H8 endpoint,
catch-up MSE versus SmoothL1 beta1.0 only,all H9 gates unchanged. Next is implementation
audit,design lock,preflight and canonical rearm. H9 remains terminal INCONCLUSIVE;its
partial checkpoint and the CAL benchmark-copy path are forbidden as H10 sources.

Reference sources:

- Paper page: https://ojs.aaai.org/index.php/AAAI/article/view/20394
- Paper PDF: https://cdn.aaai.org/ojs/20394/20394-13-24407-1-2-20220628.pdf
- The paper reports an end-to-end RL HUNL agent using pseudo-siamese state encoders, Trinal-Clip PPO, K-best self-play, and Slumbot evaluation. It reports about `111.56 mbb/hand` versus Slumbot, which is about `11.156 bb/100`.

## Canonical Speed & Training-Method Workflow (2026-07-06)

Five documents now govern ALL speed and training-method work on the V5 track. Read them
before proposing or applying any trainer/env change; they are mandatory, not advisory:

1. `docs/V5_TRAINING_PLAYBOOK.md` - HOW to operate: the loop, experiment lifecycle
   (register -> validate -> cutover -> judge -> record), signal-resolution table (what each
   metric may/may not justify), speed gates, method gates, incident response, and the
   short list of things that still require user escalation.
2. `reports/v5_training_method_audit_20260706.md` - WHY: code-level audit of the current
   trainer (problems S1-S4 throughput, M1-M10 method) with file:line evidence, plus the
   list of things verified CORRECT that must not be "fixed".
3. `reports/v5_method_improvement_roadmap.md` - WHAT: ranked improvements R1-R13 with
   expected gain, effort, risk, and per-item validation gates, plus an explicit
   do-NOT-do list and the recommended execution order.
4. `reports/v5_experiment_ledger.md` - RECORD: pre-registration ledger. No
   behavior-affecting change may run without a filled entry (hypothesis, gate, abort
   criteria, rollback). Seeded with EXP-001..008 in recommended order.
5. `docs/V5_POKER_RESEARCHER_DECISION_CONTRACT.md` - INFERENCE: separates
   realized-loss localization, association, counterfactual action regret, same-start
   method effects, cross-play cycles, and formal external strength. Read it before
   converting any hand review, action frequency, value audit, or policy swing into a
   causal diagnosis or experiment selection.

Standing rules distilled (full versions in the playbook):
- One behavior-affecting change per continuation window; judged only at its registered gate.
- Build EXP-001 (mirrored-deal internal eval) FIRST - it is the measuring stick; without
  it no method experiment can be judged.
- Effects must exceed the signal's CI to count; quick5k deltas under ~60 bb/100 and
  200-hand internal probes justify nothing.
- No new hand-crafted action priors. EXP-004's 0.005 step was rolled back; hold
  the stable floor at preflop 0.01 / postflop 0.02 while EXP-003 is open. A
  further decay or zero-prior step requires a new explicit registration.
- Throughput work (EXP-002/008) is pre-authorized when its gates pass - at ~600 h/s the
  2.7B target takes ~52 days, so speed is part of the plan, not a detour.
- Realized chip loss never identifies the EV of an unchosen action. Before any new
  behavior experiment is selected, run the reporting-only poker research review. An
  action-specific intervention additionally requires a validated counterfactual or
  same-state controlled artifact; a self-play-cycle claim requires a complete
  common-deal cross-play matrix. Missing evidence fails closed rather than being filled
  by narrative agreement.

## Autonomous V5 Execution And Self-Correction

The V5 agent is expected to continue safe in-scope work without waiting for routine
operator approval. Autonomy is governed by the experiment lifecycle and evidence gates;
it is not permission to relax them.

### User blanket execution authorization (2026-07-11)

The user explicitly authorizes autonomous continuation of every action already inside
the active CardPilot goal and instructs the agent not to ask conversational approval
questions. Treat routine choices and all registered state-machine transitions as
approved, including local trainer/watcher start, stop, restart, rollback, canonical
rearm, exact-gate cutover, evaluation launch when its frozen prerequisites pass,
incident recovery, reporting/control-plane repair, tests, and handoff/Ops updates.
Continue through the registered chain without pausing for user confirmation.

This authorization does not weaken any evidence gate, immutable lock, fail-closed rule,
single-variable rule, claim standard, or objective boundary. Never interpret it as
permission to force a verdict, bypass a failed prerequisite, spend money, disclose
secrets, or silently change the project objective. If the execution platform itself
requires an approval dialog, request it through the platform tool and continue after it
is granted; do not turn it into a conversational planning question.

1. **Separate intent from mutable state.** A new user instruction controls scope and
   objectives. For mutable facts such as PID, gate, checkpoint, hands, health, quality,
   watcher coverage, and benchmark status, exact live artifacts override numeric values
   copied into a prompt, handoff, or static snapshot.
2. **Detect stale instructions before acting.** If an immediate step names a gate,
   checkpoint, PID, or pending implementation that live artifacts show is already
   completed or superseded, label that step `STALE_OPERATIONAL_STATE`, preserve its
   intent, and continue from the next valid state-machine transition. Never replay a
   missed historical gate or relaunch a completed measurement merely to satisfy stale
   wording.
3. **Use this truth order for operational facts:** exact identity-bound result/gate
   artifact; active-run manifest/health/dashboard/queue/cadence; current goal and latest
   handoff; static AGENTS snapshot; historical notes. A conflict at the same tier fails
   closed until identity is resolved. Do not copy, impute, or reinterpret mismatched
   fields.
4. **Self-correct reporting and control-plane defects.** The agent may autonomously
   diagnose and repair reporting-only races, stale aliases, watcher gaps, duplicate-safe
   launch controls, provenance checks, tests, and documentation. Preserve original
   artifacts and append an Ops CENSURE/correction row; never rewrite the append-only Ops
   history. Re-run focused and full relevant tests before declaring the repair valid.
5. **Continue already-authorized operations autonomously.** The agent may refresh
   dashboards/queues, run reporting-only probes, canonically rearm watchers, quarantine
   stale artifacts, and allow registered duplicate-safe cadence launches when their exact
   gates pass. It must not restart the trainer for inspection, manually bypass cadence,
   or override health/quality/provenance checks.
6. **A behavior change may be implemented and cut over without another user prompt only
   when every condition is true:** the previous behavior window is terminal; one exact
   change is selected by the registered decision rule; a complete ledger registration
   freezes hypothesis/baseline/window/gates/abort/rollback; offline validation passes;
   the cutover source is an exact PASS checkpoint; rollback artifacts and watcher rearm
   are ready; and the change is outside the user-escalation list. If any item is missing,
   remain `BLOCKED` or `WAITING` and finish the missing safe preparation instead of
   improvising.
7. **Diagnose causally before registering the next method.** Build an evidence matrix
   across official Slumbot loss cuts, repeated preflop/selector behavior, internal
   localization, training dynamics, and code-level mechanism. Distinguish upstream
   causes from downstream symptoms and prefer the smallest upstream single-variable
   experiment. A point estimate, a 200-hand probe, or an appealing narrative is not a
   registration gate. Apply `docs/V5_POKER_RESEARCHER_DECISION_CONTRACT.md`: raw
   hero-fold/line/hole-family losses are observational only; one seed supports at most a
   conditional method conclusion; action regret and temporal cycles require their exact
   validated artifacts. `v5_poker_research_review.py` never launches behavior, but its
   fail-closed permissions must be read before method selection.
8. **Permit re-ranking, forbid post-hoc redesign.** Before registration, new frozen
   evidence may change which candidate is next. After registration or launch, do not
   alter the selected variable, sample count, seed, success threshold, deadline, or
   interpretation. Judge `PASS`, `FAIL`, or `INCONCLUSIVE` exactly as registered, then
   adopt or roll back.
9. **Refresh the mutable handoff after material transitions.** After a gate window,
   incident, experiment judgment, official Slumbot bundle, cutover, rollback, or watcher
   rearm, update the current goal/handoff and append exactly one reconstructable Ops row.
   Keep invariant rules separate from the mutable snapshot so an old gate number cannot
   become a permanent command.
10. **Never self-correct by changing the objective.** The agent may not weaken the
    L5/L6 claim rule, change official greedy-direct policy, reopen EXP-003, add adaptive
    measurement samples, decay the prior without registration, bundle behavior changes,
    or enter V6 architecture/observation work without the explicitly required user
    escalation. The from-zero constraint was LIFTED by explicit user escalation on
    2026-07-11 (ledger event `v5-user-route-escalation-hybrid-goal-20260711`); the 2.7B
    figure remains a resource cap only, never continuation authority.
11. **Enforce cross-task live-run isolation.** While any registered trainer arm is
    active, do not spawn or delegate project-execution work. Delegated review is limited
    to file reads, hashes and process listing and must state the active trainer plus
    forbidden process classes. Do not execute planner, evaluator, benchmark, mirror,
    validate-only or related project scripts, and do not run commands containing
    `slumbot`, `v5_slumbot`, `mirror` or `evaluator` tokens unless the exact active design
    lock authorizes them. The parent agent is responsible for every delegated action.

## Latest Takeover Handoff

Authoritative live update (2026-07-15): user goal v2 is active. H9 is permanently
`INCONCLUSIVE / H9_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION`; judgment SHA
`dd1ada4c08058b2d479b5b8fa80b6c0880df71c49b70b6d0fc401c1e562d3fe6`, terminal
audit SHA `54d782f684dd091e4e095537231a9bfdee6575714341b4baef0476800cc02ee2`
and incident SHA `e2f1acc0f32f0cffd3fa9b31a3da040b44977a2c0cf9ee40016f255d548d3fa6`.
Never resume,reclassify,evaluate or use H9 for method/strength inference. External debt
is51,537,004 hands,so `EXTERNAL_DEBT_GATE` blocks every new behavior window until
`CAL-EXT-001_H8_TREATMENT_GREEDY_QUICK5K` completes on exact H8 endpoint iter33834 /
556,011,085, SHA `7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`,
greedy-direct4x1,250 with full bundle. Pre-CAL Route Review006 result SHA
`f9aa625c8209c78662d1ac687f595d94e37a57c755f597923c2a9b1eb2467a4b` and H10
prereg SHA `9ca522b4a84b3cc0daa5a3ad326d87ebfa909a064c4ce36cb92284b34152b6a1`
are preserved but `SUPERSEDED_PRE_CAL_EXT` with no authority. After CAL-EXT-001,run a
new registered/audited Route Review006 before any H10 lifecycle. Goal-v2 activation
artifact is `reports/v5_campaign_goal_v2_activation_20260715.json`. Latest official
strength remains L0:20,400 hands,-153.2999 bb/100,CI[-187.6945,-118.9052]. Path-1
coordinator37656 remains detached CPU-only diagnostic;do not restart,expand,ingest or
move it to GPU. The H9-running paragraph immediately below is historical.

Authoritative live update (2026-07-14): H9 fresh control
`v5_hybrid_h9_control_catchmse_same33834_20m_r1_20260714` is running as PID49380
from exact H8 treatment source iter33834 /556,011,085,checkpoint SHA
`7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`.
Prereg SHA `05bcb04a34cff546cce2159ecdee3e31850c54e0f8a9f37accb30090a100f84b`,
design-lock SHA `30071df4fa72ddf9c4244eace4e9ed4cbe8186d7e3c53d93fde0f2044687d81e`
and preflight SHA `79d84c38264153f37ed53c88a4f05818788a9aacec62647fcb0f62dd97f6aac6`
are authoritative PASS. Fixed target576,011,085;optimizer preserved,target-KL0.03,
catch-up enabled and control loss MSE. Health/protocol PASS,isolation0,stderr0;
control first60 is frozen PASS at2043.778818 effective h/s(rows2..61),a throughput
baseline only;
canonical rearm SHA `5892f447266b48b23c22cb20859ea8533a463dc512ae02995f583c077882656d`
survival PASS with exact endpoint/protocol/treatment-launch/completion supervision and
generic/internal/Slumbot paths blocked. Reporting-only health adapter correction SHA
`5921093568c5f1839e1ea120f84cfe6d804f9776e03a5966c10c8d6aeda25c4d`
is CENSUREd,failed status/log preserved,tests22/22 PASS;trainer was untouched and no
behavior,lock or gate changed. H9 official hands0. The H9 registered-no-launch and H8
evaluation/treatment-running text immediately below is historical. Pre-cutover
control-plane correction SHA
`adbd0dd26e5a7e8b3480444fc4e869a1b48c40825f5f976874d63ad4b34e9db5`
prevents a future duplicate completion supervisor by retiring the unique control
completion watcher only after treatment manifest identity PASS and before unchanged
canonical rearm;the intentionally non-locked launcher changed,not trainer behavior or
the design lock.
Locked post-arm chain static audit SHA
`c7d914802ef3a991117b215bedc1a2e9771750ae305667dd0c4ebfa16c3ef35a`
is PASS and binds measurement-lock,manifest,mirror/completion/judge tools and exact
source-anchor checkpoint identity. Semantic role `source_anchor` maps to immutable
evaluator arm alias `anchor`;evaluation remains forbidden until both H9 endpoints PASS
and no trainer is active.
Thread heartbeat automation `v5-drive-to-l5-monitor` is ACTIVE every30 minutes on this
same task. It only wakes the goal to reread exact artifacts and continue registered
transitions;it launches no local process and must not be duplicated. Remove it after
L5 PASS or route-exhaustion escalation.
Path-1 remains detached diagnostic-only and untouched. Immutable progress artifact SHA
`2b1e1a18cb1797a56a1e14d96adfbc477e7134a552534cecc32d946a3e88583`
PASSes at136/600 complete gzip/meta pairs:136 latest unique QA PASS,zero illegal
post-all-in rows and zero missing/bad metadata. Historical board211 FAIL remains preserved
and recovered to latest PASS. Coordinator37656 remains BelowNormal with six CPU workers;
no restart,expansion,GPU use,training ingestion or official hands occurred.

Authoritative live update (2026-07-14): both H8 endpoints are frozen PASS,no trainer is
active,and the locked completion supervisor is running the control fixed40k common-deal
mirror CPU-only/BelowNormal/threads1. Treatment finished at iter33834 /556,011,085,
overshoot9,799<=50,000,stderr0,official hands0;checkpoint SHA
`7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438`,
endpoint-status SHA
`de4913626d117aac50f2c09084cf636f9b08232a82dfeb8e33cbcb68d099dfb2`
PASS and protocol-status SHA
`5e265c087a9c4a8ebf1090695a879cea139ad2b556ad86d6ca4b2e908cfb6b7a`
is ARM_FINISHED_GUARDS_PASS. Measurement-lock SHA
`9b48175c3c65144f34c4ca64a678fd9311c54c4a522e4fa18c51b740caae0053`.
No verdict exists yet and official hands authorized remain0. Preregistration SHA
`ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713`
and design-lock v5 SHA
`298daa368585af79586f3ba24b7fde1ae862de41a8221cdf46c0825d041957c6`
remain authoritative. Control
`v5_hybrid_h8_control_kles003_nocatch_same32617_20m_r1_20260714` is frozen endpoint
PASS at iter33834 /556,010,507 hands, overshoot9,221<=50,000, stderr0, checkpoint SHA
`29b72c27a704b631297296025a542217c4cba1512d90e40ad3cd3da5383702d8`;
control first60 is frozen at2268.809632 effective h/s.

The treatment-running paragraphs below are historical and cannot override this locked
evaluation state.

Treatment `v5_hybrid_h8_treatment_kles003_vhcatch_same32617_20m_r1_20260714` runs as
PID40760 from the exact same H7 source iter32617 /536,001,286, SHA
`948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149`.
Its target is556,001,286, optimizer preserved,target-KL0.03 and the sole variable is
value-head catch-up enabled. Health and protocol guards are PASS,stderr0,isolation0.
Treatment first60 is frozen PASS at1983.817894 effective h/s; ratio0.8743871084>=0.85
versus control2268.809632. Immutable status SHA
`bedd4575defbd769227f568530f375409686b5a6d9538f2ec053f877d2aad918`, metrics SHA
`8475b9955b214cc74af2082cc500736763b9b6026c0b8eb8731fdbaa67d078b5` and audit SHA
`e07794e74a27305bda1055ce6e4e3a6305b60a99a1a0dd954449680e50bb1066`
PASS. This is protocol-only evidence; treatment continues fixed20M. Canonical rearm SHA
`d55f77f5577c1701e25053bf00debf472b8bf16ba7c0ee4d1b521a7f1332ba8c`
has survival PASS and eight generic/Slumbot paths blocked. No evaluation may start until
both endpoints are frozen PASS and no trainer is active.

A reporting-only captured-pipe stall left the one-shot launch supervisor at INVOKING
after exact treatment/rearm had materialized. The stale state was preserved, only that
supervisor was stopped, and the immutable locked script was unchanged. Correction SHA
`5ba7c629662fccb81fcfa733f2ffa610766f565ca444dd22928407a1e9c93a49`;
recovered launch-status SHA
`4550361e2401d815508fd60c79d979fd5987467732f5f844b5abdb60816713c5`.
This changes no behavior or judgment authority. Prior health reporting corrections remain
CENSUREd at SHA `86bfea852188b1e9972ae0854c50f9194b44b757e9c9745d18e0ff65a64eba1d`
and `b377b09444a5237f98fb61a6ffb9ed3dc1fbeed230c298892e1311b1a221fd2d`.
The treatment protocol watcher later exited on a Windows atomic status-file replace
race;trainer and endpoint/completion supervision remained alive. Canonical rearm restored
protocol PID33728 with survival PASS. CENSURE artifact SHA
`6c663d00662593113edce5dc3ce3ec8286415f9d6ea75b0f36bec346e1006034`
records the unsnapshotted mutable pre-rearm stderr/status;post-rearm lock audit SHA
`b848ab3171270ddecc7745da8e30b2b4a4bf3f1f443cfe057f39725b875b7f09` PASS.
Path-1 remains untouched at121/600 QA-PASS, coordinator37656, six CPU-only/BelowNormal
workers, artifact SHA
`cdbf77e13f011413fc6a3fff7f8686e688da493b78d82aa8d19b959019dbfe52`.
H8 authorizes official hands0. Current goal SHA is
`c365deca12959aabb64df0f6df08311fab50fc31ea7c240cb48df791222cd599`;
handoff MD SHA `25309b9441d198f13068837bb1bf319af0660f13089632525213e1a7c225d635`
and JSON SHA `88fdadff33916b3369bce15ef8011ef5adfaa474787de67dc4bc5c76923103ff`.
Older H8 control-running, `REGISTERED_NO_LAUNCH`, no-process and H7-running paragraphs
below are historical.

Latest authoritative correction (2026-07-14): H7 remains terminal
`FAIL / H7_FAIL_REGISTERED_GATE`. Formal Route Review 004 result SHA
`126dfc461c822c4b2bb4e599ac3da276b6412a9dda210ba8912a8d97fc0a6859` is
`PASS_ROUTE_REVIEW`, `route_exhausted=false`, and selects
`H8_VALUE_HEAD_ONLY_CATCHUP_AFTER_KL_STOP`. H8 preregistration SHA
`ecc7f9bc30918c8a2c0b07dbe6ca8dd5d06cdfc6bd3e71b45b543a80e33d5713` is immutable
`REGISTERED_NO_LAUNCH`. Its fresh same-start 20M arms both use target-KL0.03 from the
exact H7 treatment endpoint; only treatment enables value-head-only catch-up after KL
early stop. Launch is blocked until implementation, independent audit, design lock,
preflight, and canonical rearm pass. No Python trainer/watcher/mirror/Path-1 process was
observed; revalidate Path-1 identity before resume. H8 authorizes zero official hands.
The intermediate research-review `PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` text
below is historical prerequisite evidence and not the final Route Review 004 authority.

Superseding authoritative update (2026-07-14): H7 is terminal
`FAIL / H7_FAIL_REGISTERED_GATE`. Judgment SHA
`6d0e2ae773ca79c57606d5de6765e67ed2c12aba92be41611f44a2c6ba581304` and immutable
audit SHA `89382ddb7fadd319cd77afb6cad106182735401b1e37034657c67e94466c5027` are authoritative.
The fixed40k mirror passed, but registered endpoint normalized-MSE and KL-p95 gates
failed. Route Review 004 SHA
`e8df3c12876aaf1f38cd88a652bc1ca87f42ba4fab3f83235213f2a61a9efef9` is
`PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET` / `TIER2_FROZEN_ROUTE_PIVOT` and
authorizes no new behavior or official hands. A read-only process check at
`2026-07-14T07:26:03Z` found no Python trainer, watcher, mirror, or Path-1 process;
revalidate exact identity before any Path-1 resume. Latest official strength remains
L0:20,400 greedy-direct hands,-153.2999 bb/100,CI[-187.6945,-118.9052]. The older H7
control-mirror-running text below is historical and must not override this update.

The authoritative current goal and short handoff are
docs/V5_CURRENT_GOAL.md,
reports/v5_alpha_holdem_takeover_handoff_20260711.md, and
reports/v5_alpha_holdem_takeover_handoff_20260711.json.

Current authoritative update (2026-07-13): the standing DRIVE-TO-L5 campaign is active.
Current `docs/V5_CURRENT_GOAL.md` SHA256 is
`6782068f28fd5cf620ea806bb714ce6afbc665eced4860be544afd577ce20339`.
H1/H2 are terminal FAIL; H3 adapter v2/v3 are terminal FAIL_CLOSED; H4 is terminal
INCONCLUSIVE/NO_CANDIDATE_NO_LAUNCH; H5 is readiness-incomplete; H6 is terminal
`H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT`. H6 judgment SHA
`25950437f46dbda6ec7c07d61db61c9c5630061868769d6723116cd2a2677053` and audit SHA
`0adcc3326b3934072a31757ba8319839afa7a2346db4c7f3350ce9263518d867` are immutable.

Route Review 003 result SHA
`cdf17d3cdaba749cc881e7c48fd37a9a6dbcf3b3aac82cee46473415678d9f99`
selects H7 fresh contemporaneous A/B with all evaluation deferred and says
route_exhausted=false. H7 preregistration SHA
`45b57f4fe817f1b98e7267a8e482d46b8121fb41d4e432a8af25a1857c6cb4b7` and design
lock SHA `88aea213e00614191b79496079ea8607aca67a0a7d9c582f47a93af011f325af`
are authoritative. Fresh control `v5_hybrid_h7_control_kl0_same31400_20m_r1_20260713`
is frozen PASS at iter32617 /536,005,488,checkpoint SHA
`468f7a854e59387f2dda3bef7287a934a31d0ef75a5ec402db18bce02290d71b`.
Its first60 is frozen PASS at1085.698240 effective h/s. Exact treatment
`v5_hybrid_h7_treatment_kles003_same31400_20m_r1_20260713` is frozen PASS at iter32617
/536,001,286,checkpoint SHA `948050ac6d273ec2cd1291b3e1b430d4c747ea918f5c1820edf18397a6829149`.
First60 ratio0.993533739 is frozen PASS; both trainers are stopped. Fixed40k control mirror
PID20552 is running CPU-only/BelowNormal under the immutable measurement lock; all
generic/Slumbot paths remain terminally blocked.
A reporting-only null-total-hands formatter crash was CENSUREd, tested3/3 and restored
through canonical rearm; it changed no trainer, gate, endpoint evidence or verdict authority.
No endpoint evaluation or mirror may run until treatment freezes PASS and no trainer
is active. No extension,second seed,later endpoint or official hands during H7.
Control/launch artifact SHA
`c81b53dcb2a6e1c80efa12f6f98cc5e0d53e7e59025a5c03768ca81e0ba53564`.
Live control-plane audit SHA
`792f9a460ec093f88fd5cb62e3c6121b18e988f6e4f9f581b4392a091bd78537`
is reporting-only PASS18/18 and changed no locked tool or process.

Path-1 legal-all-in successor remains detached CPU-only diagnostic provenance toward
600 boards and is not v5.5-training eligible. Thirty boards are QA-PASS with zero
missing/illegal post-all-in rows; the unchanged six workers continue123/127/131/132/136/137.
During H7 arms do not restart,expand or add workers; do not ingest it without new frozen
H3 evidence.
The older H1 `REGISTERED_NO_LAUNCH` paragraph immediately below is historical and must
not override this update or the current goal/handoff files.

Historical pre-H1 paragraph retained below: the user escalation on 2026-07-11 remains authoritative and the
from-zero constraint is LIFTED (ledger event
`v5-user-route-escalation-hybrid-goal-20260711`). Historical goal snapshot
`docs/V5_CURRENT_GOAL.md` SHA256
`533ef5359dcccdb7a8420df0c59482b560d5108005f3f1cfc384140799c3d228` defines the
HYBRID H1→H5 route and unchanged L5/L6 claim contract. H1 is now exactly
`REGISTERED_NO_LAUNCH`: immutable preregistration
`reports/v5_hybrid_h1_preregistration_20260711.json` SHA256
`bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab`,
independent audit-v2 21/21 SHA `eef20d4373e012f9232163c9cc902a62e07de9d34743f243e35680c909ccca0f` PASS and tamper/authority tests12/12 PASS. Its one integrated critic-v2
window changes critic units to fixed effective-stack fractions (/200; PopArt forbidden),
uses a detached deep 256→256→128→1 value head, and retunes value_coef0.5→1.0.
Fresh same-start critic-v1 control and critic-v2 treatment are fixed20M each from exact
gate31400; EXP-W1/EXP005-C endpoints are not reused. H1-CAL-001 is a frozen10k
common-deal-pair holdout; PASS requires normalized MSE reduction point≥15% and
bootstrap95% lower≥10%, h/s ratio≥0.85 and entropy non-inferior. H1 authorizes zero
official hands and no V4/L5/L6 claim. All trainer/watchers remain stopped and launch
authority is NONE. Next is critic-v2 plus H1-CAL-001 implementation/offline validation,
then a separate immutable design lock and canonical blocked-watcher preflight. Do not
launch either arm until every preflight passes. EXP005-C and EXP-W1 remain permanently
terminal. Latest official strength remains L0: 20,400 greedy-direct hands,
-153.2999 bb/100, CI[-187.6945,-118.9052].The older `v5_alpha_holdem_takeover_handoff_20260706_1224.*` files and the
historical snapshots below are retained only for audit context and must not be
used as current instructions.

Older historical bullets below are retained for context and should not override the latest takeover handoff or current status files.

- Checked at `2026-07-06 09:25 EDT`. Trainer PID `56876` was active and was not restarted. Do not stop, restart, or replace this trainer just to inspect progress.
- Active run dir: `models/alpha_holdem_v5_from_zero/v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`.
- Latest dashboard read: checked_at `2026-07-06T13:23:46.710179+00:00`, live iter/hands `8832` / `144,919,423`, checkpoint iter/hands `8800` / `144,394,363`, recent throughput `772.76 h/s`, next gate `8900` pending, next external Slumbot `quick5k_150M`, remaining checkpoint hands `5,605,637`.
- Latest completed post-gate review is `v5_post_gate_review_8800.json`: `REVIEW_REQUIRED_NO_AUTO_RESTART`; gate PASS; internal `REGRESSION_RISK_INTERNAL`; delta mean/lower versus 8600 `-812.125` / `-1039.408`; preflop probe WARN with `1` warning; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; strength `NOT_PROVEN_STRONGER_THAN_V4`.
- Latest official Slumbot evidence remains 100M quick5k greedy: `5,000` hands, `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, promotion gate FAIL, L0. This is not stronger than V4 and not close to the Slumbot/L5/L6 claim gate.
- Slumbot analysis coverage was backfilled. `v5_trend_ledger.json` now reports `WARN_HISTORICAL_INCOMPLETE`, complete/total `6/7`. Complete milestones: 59M, 62M, 65M, 72M, 75M, 100M. The only incomplete milestone is 50M because its decision dump JSONL files are missing; it cannot support action-level loss analysis or tuning.
- Backfill was reporting-only. It generated historical loss reports, artifact audits, hand reviews, and refreshed `v5_trend_ledger.json`. It did not run new Slumbot hands, change model weights, change training parameters, or restart trainer/watchers.
- Next AI should first read `v5_dashboard_watch_status.json`, `v5_next_action_queue.json`, `v5_trend_ledger.json`, `v5_eval_cadence_watch_status.json`, latest `gate_*_status.json`, and latest `v5_post_gate_review_*.json`. Then wait for `gate_8900` unless the user explicitly changes scope.

## User-Mandated AlphaHoldem Workflow

This section is the canonical operating contract for the AlphaHoldem V5/Slumbot track. It takes precedence over stale historical notes elsewhere in this file.

1. Work on the AlphaHoldem V5-from-zero Slumbot model unless the user explicitly switches scope. Do not confuse this with a 200bb SRP CFR asset build.
2. Use the AlphaHoldem AAAI 2022 paper as the reference method: end-to-end RL for HUNL, PPO/Trinal-Clip-style training, K-best historical self-play, and Slumbot evaluation. Engineering changes are allowed, but only when logged, reversible, and benchmarked.
3. The final target is a general 200bb HUNL greedy policy that can play complete hands against Slumbot. The stretch benchmark is the paper-scale result of about `+111.56 mbb/hand`, or `+11.156 bb/100`, against Slumbot.
4. Keep training running at maximum stable throughput. Optimize speed through health, `h/s`, worker stability, checkpoint freshness, and stderr checks; do not restart the trainer just to inspect progress.
5. Test while training continues. Required staged evidence is health/gates, internal probes, selector-pair diagnostics, quick5k Slumbot screens, promotion20k screens, and formal100k Slumbot screens.
6. Official strength evaluation is greedy policy versus Slumbot. Callguard, guarded, sampled, or mixed selectors are diagnostics unless the user explicitly changes the policy contract.
7. Every Slumbot match must retain hand-level evidence. A benchmark is incomplete unless hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, and hand-review JSON/MD all exist.
8. After each Slumbot result, analyze where chips were lost before changing training: SB versus BB, terminal bucket, street, first preflop decision, SB open rates, BB facing-open rates, top losing lines, and hole-family losses.
9. Compare every new result with V4, previous V5 checkpoints, and the AlphaHoldem paper target. Report the evidence class: formal, promotion-scale, quick-screen, selector diagnostic, or internal-only.
10. Do not tune from `bb/100` alone. Change training only when Slumbot loss reports, preflop probes, selector diagnostics, and training health point to the same stable leak.
11. Before any training intervention, write or read a reviewed intervention plan. Prefer context-conditioned changes when SB first-action leaks and BB facing-open leaks point in different directions. Do not silently switch official evaluation to callguard.
12. Validate any intervention with the same loop: health gate, internal probe, selector-pair diagnostic when relevant, next Slumbot screen, artifact audit, and hand-loss review.
13. Acceptance criteria are evidence gates, not total training hands. L5 requires at least `100,000` official greedy Slumbot hands, `bb/100 > 0`, and 95% CI lower bound `> 0`. L6 additionally requires performance near the paper target, about `+11.1 bb/100`.
14. When answering progress or strength questions, first reread local state and report exact numbers: run id, checkpoint, training hands, `h/s`, health, benchmark hands, `bb/100`, CI lower/upper, policy mode, and whether the result is official or diagnostic.

## Model Disambiguation

Do not confuse the active AlphaHoldem V5 run with a 200bb SRP CFR asset build.

- Active target model: AlphaHoldem-style V5-from-zero, 200bb HUNL, single forward-pass policy, PPO/Trinal-Clip-style update, K-best historical self-play, evaluated against Slumbot.
- CFR/SRP assets: auxiliary baselines, teachers, diagnostics, or research assets only unless the user explicitly changes the objective.
- Final deliverable for this track is not a SRP-only or CFR-only player. It is a general 200bb HUNL policy that can play full hands against Slumbot.
- If the user asks "this model" and both V5 and a CFR asset could match, identify the run id/checkpoint before answering.
- Training hands such as `2.7B` are compute budget targets, not acceptance criteria. Acceptance is based on Slumbot evidence, CI, and hand-review quality.

## Non-Negotiable V5 Workflows

These workflows are mandatory for any agent continuing the AlphaHoldem V5/Slumbot track.

1. First re-read local state. Do not answer from memory. Check the active run directory, trainer PID, latest checkpoint, health, h/s, watcher processes, latest gate, latest Slumbot status, and latest loss reports.
2. Keep the trainer running at maximum stable throughput unless a documented intervention decision requires a restart. Never restart the trainer just to inspect status.
3. Test while training continues. Use staged evidence: health watcher, checkpoint gates, internal probes, selector-pair diagnostics, quick5k Slumbot screens, promotion20k screens, then formal100k screens.
4. Treat every Slumbot benchmark as a hand-review job. The benchmark is incomplete unless hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, and loss report JSON/MD all exist.
5. Preserve Slumbot hand records. Never discard or overwrite hand-level evidence before analysis. If artifacts are missing or stale, rerun or repair the benchmark pipeline before trusting the score.
6. Analyze why chips were lost before changing training. Review position split, terminal bucket, street, first preflop decision, SB open rates, BB facing-open rates, top losing lines, and hole-family losses.
7. Compare every result against V4, previous V5 checkpoints, and the AlphaHoldem paper target. Report whether the evidence is official, promotion-scale, quick-screen, diagnostic, or internal-only.
8. Do not tune from bb/100 alone. Change training only when multiple evidence sources agree on a stable leak: Slumbot loss reports, preflop probes, selector-pair diagnostics, and training health.
9. Keep official strength evaluation on greedy policy. Callguard, guarded, sample, or other selector variants are diagnostics unless the project explicitly changes the policy contract.
10. Do not claim "stronger than V4", "beats Slumbot", L5, or L6 without formal evidence. L5 requires 100k+ official greedy Slumbot hands, bb/100 > 0, and CI lower > 0. L6 also requires performance near the paper target, about `+11.1 bb/100`.

## Required V5 Closed Loop

This is the required workflow for the user's questions: "is it better than V4", "is it approaching Slumbot", "is every checkpoint improving", and "should training be adjusted".

1. Train continuously unless there is a documented restart/intervention decision. Keep speed maximized through stable `h/s`, healthy workers, clean stderr, and non-stale checkpoints.
2. Evaluate while training continues. Use local health/gates and internal probes for cheap regression checks, selector-pair runs for leak localization, quick5k Slumbot for smoke/regression, promotion20k for candidate promotion, and formal100k for claims.
3. Freeze checkpoints for Slumbot. Do not benchmark live unsaved weights, and do not mix policy modes when comparing results.
4. For every Slumbot run, preserve hand-level evidence: `*_hands.jsonl`, `*_dump.jsonl`, CI summary, promotion gate, dump analysis, and loss report JSON/MD. A score without these artifacts is incomplete.
5. After every Slumbot run, analyze where chips were lost before changing training: SB vs BB, terminal bucket, street, first preflop decision, SB open rates, BB facing-open rates, top losing lines, and hole-family losses.
6. Compare the new result against V4, previous V5 checkpoints, and the AlphaHoldem paper target. Label the evidence as formal, promotion-scale, quick-screen, selector diagnostic, or internal-only.
7. Tune only when multiple sources agree on the same stable leak: Slumbot loss report, preflop probe, selector-pair diagnostic, and training health. Do not tune from `bb/100` alone.
8. If tuning is needed, write a reviewed intervention plan first. Prefer context-conditioned changes when SB first action and BB facing-open point in different directions. Do not apply a blanket preflop prior or switch official policy to callguard unless explicitly approved.
9. Validate any intervention with the same loop: health gate, internal probe, selector-pair diagnostic if relevant, next Slumbot screen, and hand-loss review.
10. Only promote claims through evidence gates. V4 improvement, Slumbot-positive strength, L5, and L6 require Slumbot evidence with enough hands and CI; training loss, self-play reward, internal probes, and 2k/5k diagnostics cannot prove those claims.

## Slumbot Hand-Log Review And Tuning Loop

Every Slumbot run is a benchmark plus a hand-review job. Do not treat a score as complete unless the full evidence bundle exists and has been reviewed.

1. Freeze a saved checkpoint before the match. Do not benchmark unsaved live weights.
2. Run the intended policy mode and label it clearly. Greedy is official evidence; callguard/guarded/sample/mixed selectors are diagnostics unless the user explicitly changes the official contract.
3. Preserve all hand-level artifacts: hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, hand review JSON/MD, and selector replay outputs when applicable.
4. Audit artifacts immediately. A Slumbot result with missing hands, missing decision dumps, missing audit, or missing hand review is incomplete and cannot drive a training decision.
5. Analyze where chips were lost: SB versus BB, terminal bucket, street, first preflop decision, SB open fold/call/raise/all-in, BB facing-open call/raise, top losing lines, hole-family losses, showdown loss, all-in runout loss, and hero-fold/opponent-fold balance.
6. Compare the result to V4, prior V5 checkpoints, the previous same-policy checkpoint, and the AlphaHoldem paper target of about `+11.156 bb/100` versus Slumbot.
7. Classify the evidence before reporting it: formal100k, promotion20k, quick5k, selector-pair diagnostic, or internal-only.
8. Decide whether to tune only after multiple sources agree on the same stable leak: Slumbot hand review/loss report, preflop probe, selector-pair diagnostic, and training health. A single point estimate or wide-CI diagnostic is not enough.
9. If tuning is justified, write an intervention plan first with the exact leak, proposed parameter or workflow change, expected effect, rollback path, and validation gate.
10. After tuning, validate with the same loop before making any strength claim.

## AlphaHoldem V5 Agent Handoff Checklist

Use this checklist when taking over the thread or answering the user's recurring questions about progress, speed, strength, and whether to tune.

1. Confirm scope first: this is the AlphaHoldem V5-from-zero Slumbot track, not the 200bb SRP CFR asset build, unless the user explicitly changes scope.
2. Reread current local state before answering. Check trainer PID, watcher PIDs, latest checkpoint, training hands, `h/s`, health, stderr, latest gate, latest internal probe, latest Slumbot status, latest selector-pair status, and newest loss/hand-review reports.
3. Keep the trainer alive and optimize for maximum stable throughput. Do not restart training only to inspect progress. If throughput looks weak, inspect health, stderr, GPU utilization, worker stability, checkpoint freshness, and watcher contention before proposing a restart or sweep.
4. Evaluate continuously in staged order: health and checkpoint gates, internal fixed-opponent probes, selector-pair diagnostics, quick5k Slumbot screens, promotion20k screens, then formal100k Slumbot screens.
5. Preserve every Slumbot hand. A Slumbot benchmark is incomplete unless hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, and hand-review JSON/MD exist and are fresh.
6. After every Slumbot result, analyze why chips were lost before changing training. Required cuts are SB versus BB, terminal bucket, street, first preflop decision, SB open fold/call/raise/all-in, BB facing-open call/raise, top losing lines, and hole-family losses.
7. Compare every result against V4, previous V5 checkpoints, and the AlphaHoldem paper target. Label evidence as formal, promotion-scale, quick-screen, selector diagnostic, or internal-only.
8. Tune only when multiple sources agree on the same stable leak: Slumbot hand review/loss report, preflop probe, selector-pair diagnostic, and training health. A better `bb/100` point estimate alone is not an intervention trigger.
9. Keep official strength evaluation on greedy policy versus Slumbot. Callguard, guarded, sampled, and mixed selectors are diagnostics unless the user explicitly changes the official policy contract.
10. Use the AlphaHoldem AAAI 2022 paper as the reference method: end-to-end HUNL RL, PPO/Trinal-Clip-style training, K-best self-play, and Slumbot evaluation. Engineering deviations are allowed only when logged, reversible, and benchmarked.
11. Acceptance is evidence-gated. L5 requires at least `100,000` official greedy Slumbot hands, `bb/100 > 0`, and 95% CI lower bound `> 0`. L6 additionally requires performance near the paper result, about `+111.56 mbb/hand` or `+11.156 bb/100`.
12. When reporting progress or strength, include exact numbers: run id, checkpoint, training hands, `h/s`, health, benchmark hands, `bb/100`, CI lower/upper, policy mode, artifact completeness, and whether the claim is official or diagnostic.

Reference method: reproduce AlphaHoldem's end-to-end RL approach from the AAAI 2022 paper, including PPO/Trinal-Clip-style training and K-best self-play, but allow pragmatic engineering adjustments when they are logged, benchmarked, and reversible. The final target is a general 200bb HUNL greedy policy that can beat Slumbot, not a SRP-only/CFR-only asset.

## Last Known V5 Snapshot

This is a handoff snapshot, not a source of truth. Always reread the status files before answering current progress.

- Latest direct check at `2026-07-06T13:15Z`: trainer PID `56876` is still active and was not restarted. Dashboard watcher PID `50348`, gate watcher PID `7988`, internal watcher PID `57068`, eval cadence watcher PID `41668`, promotion20k watcher PID `56144`, formal100k watcher PID `39752`, and checkpoint archive watcher PID `38004` are active. `gate_8800` passed at checkpoint iter/hands `8800` / `144,394,363` with health `PASS`; current next gate is `8900`, `PENDING`, latest dashboard live iter `8815`, checkpoint iter `8800`. `internal_strength_probe_iter8800_200h.json/md` completed via active watcher `internal_strength_watch_7200_9200_status.json`; latest internal verdict is `REGRESSION_RISK_INTERNAL`, mean latest `-108.0 bb/100`, mean lower `-735.875`, delta mean/lower versus 8600 `-812.125` / `-1039.408`, latest best `0/2`. Rows: latest 8800 scored aggressive `-288.75 bb/100` with CI about `+/-961.89`, call-station `+72.75 bb/100` with CI about `+/-293.87`. `v5_post_gate_review_8800.json/md` is `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal COMPLETED but regression-risk, preflop probe `WARN` with 1 warning, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, strength `NOT_PROVEN_STRONGER_THAN_V4`. Queue recommendation is now wait for `gate_8900`; `internal_probe_9000` is next scheduled internal target. `v5_run_dashboard.py` now exposes the selected internal watcher status path, and `v5_dashboard_watch.py` mirrors `internal_watch_selected_status_path`, `internal_watch_latest_probe_target`, and `internal_watch_next_target`; verified dashboard status points at `internal_strength_watch_7200_9200_status.json`. Latest official Slumbot evidence is unchanged: 100M quick5k, `5,000` greedy hands, `-85.037 bb/100`, CI `[-129.224, -40.851]`, L0. Eval cadence and dashboard previews were refreshed after gate 8800: next external Slumbot remains `quick5k_150M`, checkpoint hands `144,394,363 < 150,000,000`, remaining checkpoint hands `5,605,637`, preview `WRITTEN/BLOCKED` only on `training_hands`.
- Latest direct check at `2026-07-06T13:02Z`: trainer PID `56876` is still active and was not restarted. Dashboard watcher was reporting-only reloaded from PID `25796` to PID `41212` after the Slumbot coverage alias update; eval cadence watcher PID `41668`, gate watcher PID `7988`, and internal watcher PID `57068` were not touched. `gate_8800` remains `PENDING` with health `PASS`; the latest direct gate read before reload was live iter `8773` / `143,951,225` hands, checkpoint iter `8700` / `142,753,336` hands, and `27` live iterations remaining. Eval cadence remains `WAITING_FOR_TARGET`: next external Slumbot screen is `quick5k_150M`, checkpoint hands `142,753,336 < 150,000,000`, and plan preview `WRITTEN/BLOCKED` only on `training_hands`. `v5_run_dashboard.json` continues to show the same 150M plan preview under `watchers.eval_cadence_watch.next_external_plan_preview`; no Slumbot run was launched. Slumbot analysis completeness audit: older quick5k screens at 50M, 59M, 62M, and 65M have CI/promotion evidence but no loss report, hand review, or artifact audit; 72M has a loss report but no hand review/audit; 75M and 100M have complete loss report, artifact audit, and hand review bundles. `v5_trend_ledger.py` writes `slumbot_analysis_coverage`, and `v5_dashboard_watch.py` now mirrors it to top-level status fields; verified dashboard status at `2026-07-06T13:01:59Z` reports coverage `WARN_HISTORICAL_INCOMPLETE`, complete/total `2/7`, incomplete `5`, latest milestone `100M`, latest complete `true`. Treat incomplete historical quick5k scores as diagnostic history only. Future Slumbot results are invalid for training decisions unless the full hand JSONL, decision dump, CI, promotion gate, dump analysis, loss report, artifact audit, and hand review are present and reviewed.
- Latest direct check at `2026-07-06T12:41Z`: trainer PID `56876` is still active and was not restarted. Dashboard watcher was reporting-only reloaded from PID `36768` to PID `50404`; gate watcher PID `7988`, internal watcher PID `57068`, eval cadence watcher PID `41668`, promotion20k watcher PID `56144`, formal100k watcher PID `39752`, and checkpoint archive watcher PID `38004` remain active. `gate_8800` is still `PENDING`; dashboard refresh at `12:41:44Z` reported live iter `8739`, checkpoint iter `8700`, next gate `8800`, remaining live iterations `62`, health `PASS`. `gate_8700` passed at checkpoint iter `8700` / `142,753,336` hands and `v5_post_gate_review_8700.json/md` remains `REVIEW_REQUIRED_NO_AUTO_RESTART`: preflop probe `PASS` with `0` warnings, checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`, internal probe `NOT_SCHEDULED` for 8700, latest internal evidence still 8600 `MIXED_INTERNAL`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Eval cadence status is `WAITING_FOR_TARGET`: checkpoint iter/hands `8700` / `142,753,336`, `quick5k_150M`, `candidate_count=0`, `launchable_key=null`, checkpoint remaining `7,246,664`. `v5_eval_cadence_watch.py` automatically refreshes the next external eval plan preview each poll, and `v5_dashboard_watch.py` now mirrors that preview to top-level dashboard fields; current preview status is `WRITTEN`, preview overall `BLOCKED`, failed checks `training_hands`, preview checkpoint iter/hands `8700` / `142,753,336`. Latest official Slumbot evidence remains 100M quick5k, `5,000` greedy hands, `-85.037 bb/100`, CI lower `-129.224`, loss-trend delta `-13.575`, L0.
- Latest verified continuation at `2026-07-06T10:59Z`: trainer PID `56876` is still active and was not restarted. Dashboard watcher PID `48156`, gate watcher PID `7988`, internal watcher PID `57068`, eval cadence watcher PID `25044`, promotion20k watcher PID `56144`, formal100k watcher PID `39752`, and checkpoint archive watcher PID `38004` remain active. Dashboard refresh reports live iter `8502` / `139,504,087` hands, checkpoint iter `8500` / `139,471,247` hands, health `PASS`, latest gate pass `8500`, and next gate `8600`.
- `gate_8600` passed at checkpoint iter `8600` / `141,112,380` hands. `v5_post_gate_review_8600.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `COMPLETED`, latest internal verdict `MIXED_INTERNAL`, preflop probe `WARN` with 3 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Internal 8600 rows are aggressive `+1416.50 bb/100` with CI about `+/-786.00`, call-station `-8.25 bb/100` with CI about `+/-15.18`; mean internal delta is `+99.602 bb/100` and lower-bound delta is `+254.739`, but this remains internal fixed-opponent evidence only and cannot prove Slumbot strength. Next gate is `8700`; next scheduled internal target is `8800`.
- `gate_8500` passed at checkpoint iter `8500` / `139,471,247` hands. `v5_post_gate_review_8500.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED`, preflop probe `WARN` with 3 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8400 to 8500, local preflop guardrails regressed: warnings `0 -> 3`, mean call delta `+0.113`, mean fold delta `-0.153`, and mean raise delta `+0.039`. Remaining warnings are SB open overlimp and BB facing-open overcall for min-open/3bb open. This is local guardrail evidence only, not Slumbot strength proof.
- `gate_8400` passed at checkpoint iter `8400` / `137,830,124` hands. `v5_post_gate_review_8400.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `COMPLETED`, preflop probe `PASS` with 0 warnings, checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8300 to 8400, local preflop guardrails improved: warnings `4 -> 0`, mean call delta `+0.435`, mean fold delta `-0.440`, and mean raise delta `+0.007`. This is local guardrail improvement only, not Slumbot strength proof.
- `gate_8300` passed at checkpoint iter `8300` / `136,189,521` hands. `v5_post_gate_review_8300.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED`, preflop probe `WARN` with 4 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8200 to 8300, local preflop guardrails regressed: warnings `2 -> 4`, mean call delta `-0.415`, mean fold delta `+0.341`, and mean raise delta `+0.072`. Remaining warnings are SB open overfold, BB facing-open overfold for min-open/3bb open, and SB-vs-3bet call suppression. This is local guardrail evidence only, not Slumbot strength proof.
- `gate_8200` passed at checkpoint iter `8200` / `134,548,675` hands. `v5_post_gate_review_8200.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `COMPLETED`, preflop probe `WARN` with 2 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8100 to 8200, local preflop guardrails improved in warning count `6 -> 2` but still showed SB open overlimp/underraise: checkpoint-delta warning count `-4`, mean call delta `+0.428`, mean fold delta `-0.289`, and mean raise delta `-0.140`. This is local guardrail evidence only, not Slumbot strength proof.
- `gate_8100` passed at checkpoint iter `8100` / `132,907,942` hands. `v5_post_gate_review_8100.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED`, preflop probe `WARN` with 6 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. From 8000 to 8100, local preflop shape partially improved but remained weak: warnings `7 -> 6`, mean call delta `+0.004`, mean fold delta `-0.041`, and mean raise delta `+0.038`. This is local guardrail evidence only, not Slumbot strength proof.
- `gate_8000` passed at checkpoint iter `8000` / `131,267,211` hands. `v5_post_gate_review_8000.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `COMPLETED`, preflop probe `WARN` with 7 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. The local preflop shape regressed from 7900 to 8000: warnings `0 -> 7`, mean call `0.0390 -> 0.0038`, mean fold `0.5087 -> 0.6725`, and mean raise `0.4523 -> 0.3237`. This is local guardrail regression evidence, not a restart trigger by itself.
- `gate_7900` passed at checkpoint iter `7900` / `129,626,380` hands. `v5_post_gate_review_7900.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED`, preflop probe `PASS` with 0 warnings, checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. The local preflop shape improved from 7800 to 7900: warnings `7 -> 0`, mean call `0.0011 -> 0.0390`, mean fold `0.7294 -> 0.5087`, and mean raise `0.2694 -> 0.4523`. This is local guardrail improvement only, not Slumbot strength proof.
- `gate_7800` passed at checkpoint iter `7800` / `127,985,463` hands. `v5_post_gate_review_7800.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `COMPLETED`, preflop probe `WARN` with 7 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. The preflop shape remained weak: mean greedy call is about `0.0011`, mean fold about `0.7294`, and mean raise about `0.2694`; treat this as local guardrail evidence only, not Slumbot proof.
- Latest internal evidence is `internal_strength_probe_iter8600_200h`, verdict `MIXED_INTERNAL`. The latest checkpoint is best versus aggressive in this small probe but not best versus call-station: aggressive `+1416.50 bb/100` with CI about `+/-786.00`, call-station `-8.25 bb/100` with CI about `+/-15.18`. Mean latest internal delta is positive, but internal fixed-opponent evidence is not Slumbot proof and cannot support V4/L5/L6 claims. Next scheduled internal target is `8800`.
- Latest official Slumbot strength evidence is unchanged: the 100M `quick5k` from frozen checkpoint iter `6100` / `100,091,135`, `5,000` greedy hands, `-85.037 bb/100`, 95% CI lower/upper `-129.224` / `-40.851`, L0, `NOT_PROVEN_STRONGER_THAN_V4`. There is still no valid V4, L5, or L6 claim.
- Next external eval remains `quick5k_150M`, waiting for checkpoint hands `150,000,000`. From checkpoint `8600`, checkpoint remaining is `8,887,620`; from the 11:44Z dashboard refresh, live remaining is about `8,805,502`. Promotion20k/formal100k remain waiting for `250,000,000`.
- Latest speed status at `2026-07-06T11:44Z`: throughput `WARN`, effective h/s latest about `631.8`, speed decision `WAIT_FOR_GATE_BEFORE_SPEED_CHANGE`. Do not run CUDA throughput sweeps while trainer PID `56876` is active; review mixed internal/preflop evidence and wait for Slumbot evidence before any controlled speed or training intervention.
- Monitoring/schema update at `2026-07-06T05:56Z`: `v5_preflop_policy_probe.py` now writes top-level `checkpoint_iteration`, `checkpoint_hands`, `warning_count`, and `failure_count`; `v5_dashboard_watch.py` backfills those aliases for cached preflop probe files. Verified on `v5_preflop_probe_latest.json`: checkpoint `7800` / `127,985,463`, warnings `7`, failures `0`. This is reporting only; it does not change trainer weights or training policy.
- Next-action queue update at `2026-07-06T11:44Z`: operational recommendation advanced to wait for `gate_8700`, with `internal_probe_8800` and 150M quick5k still queued. `internal_mixed_review_8600` and `preflop_guardrail_review_8600` are `WATCH` items; do not restart or claim strength from this mixed local evidence. This is reporting/queue logic only and does not change trainer weights or training policy.
- Dashboard schema update at `2026-07-06T11:55Z`: `v5_dashboard_watch.py` now exposes the latest completed post-gate review separately from the current pending post-gate target. Top-level status fields include `latest_completed_post_gate_review_overall`, `latest_completed_post_gate_review_target`, `latest_completed_post_gate_review_gate`, and `latest_completed_post_gate_review_internal`. Verified current dashboard status shows current `post_gate_review_target=8700` / `PENDING_EVIDENCE` while latest completed review remains target `8600`, `REVIEW_REQUIRED_NO_AUTO_RESTART`, gate `PASS`, internal `COMPLETED`. Added `scripts/alpha_holdem/test_v5_dashboard_watch.py` covering latest non-pending post-gate selection. This is reporting/test hardening only and does not change trainer weights or Slumbot results.
- Dashboard gate-alias update at `2026-07-06T12:02Z`: `v5_dashboard_watch.py` now mirrors detailed latest/next gate status to top-level status fields such as `next_gate_target_iteration`, `next_gate_overall`, `next_gate_live_iteration`, `next_gate_remaining_live_iterations`, and `next_gate_remaining_checkpoint_iterations`. Verified current status reports `next_gate_target_iteration=8700`, `next_gate_overall=PENDING`, `next_gate_remaining_live_iterations=58` from the gate file during the 12:01Z one-shot refresh. Added `scripts/alpha_holdem/test_v5_dashboard_watch.py` coverage for gate alias extraction. Dashboard watcher PID is now `47024`. This is reporting/test hardening only and does not change trainer weights or Slumbot results.
- Slumbot hand-log workflow update at `2026-07-06T07:35Z`: `v5_next_action_queue.py` now makes the external Slumbot items explicit that quick5k, promotion20k, and formal100k must preserve hand JSONL and require loss report, artifact audit, and hand review before any training adjustment. A 150M quick5k planner preview (`slumbot_cadence_quick5k_150M_plan_preview.json/md`) was generated while checkpoint hands were below `150,000,000`; its artifact manifest includes hands JSONL, loss report, artifact audit, and hand review outputs. Dashboard watcher PID `60456` was reloaded so recurring queue refreshes preserve this wording. This is reporting/queue logic only and does not launch Slumbot early.
- Slumbot latest-review queue update at `2026-07-06T07:40Z`: `v5_next_action_queue.py` now emits `slumbot_hand_review_latest`, derived from the latest official Slumbot CI path in `v5_trend_ledger.json`. Verified current item is `WATCH`: latest official Slumbot `5,000` hands at `-85.037 bb/100`, CI lower `-129.224`, hand review `PASS`, evidence class `quick_screen`, training adjustment `SMOKE_ONLY_USE_AS_ONE_SIGNAL`, artifact audit `PASS`. This keeps the latest official hand review/loss report visible before any training adjustment and will naturally point to the 150M hand review after that CI becomes latest. Dashboard watcher PID `53748` was reloaded so recurring queue refreshes preserve this item.
- Slumbot hand-review claim-blocking update at `2026-07-06T07:43Z`: `slumbot_hand_review_latest` now sets `blocks_strength_claim=true` if the latest official CI exists but hand review, loss report, or artifact audit is missing/unreadable. Current artifacts are complete, so the item remains `WATCH` with `blocks_strength_claim=false`; the formal strength claim is still blocked by the Slumbot CI rule. Dashboard watcher PID `48156` was reloaded so recurring queue refreshes preserve this claim-blocking behavior.
- Slumbot official loss-trend update at `2026-07-06T11:28Z`: `scripts/alpha_holdem/v5_trend_ledger.py` emits `official_slumbot_loss_trend` in JSON and an `Official Slumbot Loss Trend` markdown table. `scripts/alpha_holdem/v5_next_action_queue.py` emits `slumbot_loss_trend_latest`; `scripts/alpha_holdem/v5_dashboard_watch.py` mirrors the latest loss-trend status to top-level fields: status, claim-blocking flag, reason, row count, latest bb/100, delta, SB/BB split, hero-fold, and showdown. Verified current item is `WATCH` with 2 official rows, latest `-85.037 bb/100`, delta versus previous `-13.575`, SB/BB `-115.046/-55.028`, hero-fold/showdown `-167.737/-10.629`, and top preflop loss buckets `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`. Added `scripts/alpha_holdem/test_v5_next_action_queue.py` covering complete loss trend, missing hand review, missing loss trend, CI mismatch, and no latest CI. Added `scripts/alpha_holdem/test_v5_trend_ledger.py` covering official loss extraction/delta and missing sibling artifacts. Verification passed: `python -m py_compile scripts\alpha_holdem\v5_next_action_queue.py scripts\alpha_holdem\v5_trend_ledger.py scripts\alpha_holdem\v5_dashboard_watch.py scripts\alpha_holdem\test_v5_next_action_queue.py scripts\alpha_holdem\test_v5_trend_ledger.py`; `python scripts\alpha_holdem\test_v5_next_action_queue.py` ran 5 tests OK; `python scripts\alpha_holdem\test_v5_trend_ledger.py` ran 2 tests OK; real trend/queue/dashboard regeneration kept 2 official rows and `slumbot_loss_trend_latest` as `WATCH` with `blocks_strength_claim=false`. This is reporting/test hardening only and does not change trainer weights or Slumbot results.
- Monitoring/schema update at `2026-07-06T03:17Z`: `v5_l6_speed_decision.py` exposes top-level aliases for the first Slumbot milestone and remaining/ETA to `150M`, `250M`, `1B`, and paper-scale `2.7B`; `v5_dashboard_watch.py` now mirrors `effective_hps_latest`, `effective_hps_long`, speed ETA aliases, computed `next_external_eval_remaining_live_hands`, `preflop_probe_overall`, and `checkpoint_delta_overall` into `v5_dashboard_watch_status.json`. `v5_checkpoint_delta.py` now avoids empty-string case labels so `v5_checkpoint_delta.json` parses cleanly in PowerShell. This is reporting only; it does not change trainer weights or training policy.
- Internal watcher schema update at `2026-07-06T03:21Z`: `v5_internal_strength_watch.py` now writes top-level `overall`, `next_target`, `next_status`, `current_checkpoint_iteration`, `current_checkpoint_hands`, and `latest_completed_target`. It also avoids appending duplicate launch-report sections when a restarted watcher sees existing probe artifacts as `SKIPPED_EXISTS`. Verified status after the 7600 probe: completed `[7200, 7400, 7600]`, next target `7800`, next status `PENDING`; no 7700 internal probe is scheduled.
- Latest verified continuation at `2026-07-06T02:23Z`: trainer PID `56876` is still active and was not restarted. Dashboard watcher PID `39364`, gate watcher PID `7988` for `7100..9200`, internal watcher PID `42588` for `7200..9200`, eval cadence watcher PID `25044`, promotion20k watcher PID `56144`, formal100k watcher PID `39752`, and checkpoint archive watcher PID `38004` are active. Dashboard refresh reports live iter `7318` / `120,076,792` hands with checkpoint iter `7300` / `119,781,345` hands, health `PASS`, and the next action is waiting for `gate_7400`; next scheduled internal probe is `7400`.
- `gate_7300` passed at checkpoint iter `7300` / `119,781,345` hands. `v5_post_gate_review_7300.md/json` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED`, latest internal remains 7200 `REGRESSION_RISK_INTERNAL`, preflop probe `WARN` with 3 warnings, checkpoint delta `LOCAL_GUARDRAILS_MIXED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`.
- Latest internal evidence is `internal_strength_probe_iter7200_200h`, verdict `REGRESSION_RISK_INTERNAL`; next internal target is `7400`. Latest 7200 fixed-opponent rows were call-station `-16.32 bb/100` with CI about `+/-218.83`, aggressive `+985.00 bb/100` with CI about `+/-973.06`, mean about `+484.34 bb/100`, delta versus 7000 mean `-20.855`. This is local-only and cannot prove Slumbot strength.
- Latest official Slumbot strength evidence remains the 100M `quick5k`: `5,000` greedy hands, `-85.037 bb/100`, 95% CI lower `-129.224`, L0, `NOT_PROVEN_STRONGER_THAN_V4`. Next external eval is `quick5k_150M`, waiting for checkpoint hands `150,000,000`; `30,218,655` checkpoint hands remain from the saved `7300` checkpoint. Promotion20k/formal100k are waiting for `250,000,000`.
- 100M hand-log diagnosis remains the active Slumbot leak read: SB `-115.0 bb/100`, BB `-55.0`; terminal `hero_fold` `-167.7 bb/100`, showdown `-10.6`, all-in runout tiny-sample `-5454.5`, opponent fold `+348.3`. First-preflop losses are dominated by `sb_open_c` `-135.2`, `bb_vs_open_lt2.5bb_f` `-100.0`, `sb_open_raise_lt2.5bb` `-181.4`, and `bb_vs_open_lt2.5bb_c` `-81.6`. Rates are SB open fold/call/raise/all-in `0.327/0.506/0.167/0.000`, BB vs open call/raise `0.340/0.088`.
- Selector replay for the 100M quick5k matched the dump exactly for greedy policy, so the hand-log/loss-report evidence is usable. Diagnostic callguard variants mostly changed losing hands and are not a validated official policy switch. Do not apply a simple "force more BB calls" fix; current evidence points to SB first-action EV, limp-heavy/under-raised opens, BB realization, and hero-fold/postflop realization as the repeated leak bundle.
- Latest non-invasive throughput audit around `2026-07-06T02:23Z` was `WARN`: dashboard mirrors `throughput_decision=PREPARE_SWEEP_CONTROLLED_RESTART_ONLY` but `speed_decision=WAIT_FOR_GATE_BEFORE_SPEED_CHANGE`, with effective h/s about `637.3`. The bottleneck is still collection/inference scheduling rather than GPU memory or PPO, but a speed change should wait for the current `gate_7400` evidence window. `v5_throughput_audit.py` now mirrors top-level `overall`, `decision`, h/s, batching, and GPU aliases; `v5_dashboard_watch.py` forwards those aliases to `v5_dashboard_watch_status.json`; `v5_l6_speed_decision.py` discovers the next gate from `gate_*_status.json` instead of stale `gate_4400_status.json` and now writes top-level aliases for health, live/checkpoint state, throughput, next gate, first Slumbot milestone, remaining hands, and ETA. `v5_eval_cadence_watch.py` now writes top-level external-eval remaining aliases, including `next_external_eval_remaining_checkpoint_hands` and computed `next_external_eval_remaining_live_hands`; refreshed cadence now reads checkpoint `119,781,345` and 150M checkpoint remaining `30,218,655`. Dashboard watcher PID is `39364`; eval cadence watcher PID is `25044`. Trainer PID `56876` was not restarted. Do not run a CUDA sweep during the active trainer.
- `v5_evidence_watchdog.py` now mirrors direct top-level strength aliases (`strength_answer`, `strength_status`, `latest_better_answer`, `trend_answer`, latest Slumbot score/CI, and claim booleans). Verified at `2026-07-05T21:38Z`: overall `EVIDENCE_ACTIVE_STRENGTH_UNPROVEN`, `strength_answer=SAMPLE_TOO_SMALL_FOR_BASELINE_CLAIM`, `latest_better_answer=LATEST_POINT_ESTIMATE_DOWN`, latest Slumbot `5000` hands at `-85.037 bb/100`, CI lower `-129.224`, and V4/L5/L6 claim booleans all `false`.
- `v5_eval_cadence_watch.py` now mirrors compatibility aliases (`next_eval_key`, `next_stage`, `next_target_hands`, `next_state`, `next_eta`, `remaining_checkpoint_hands`) and direct external-eval aliases (`next_external_eval_key`, `next_external_eval_state`, `next_external_eval_target_hands`, `next_external_eval_remaining_checkpoint_hands`, `next_external_eval_remaining_live_hands`) at the top level of `v5_eval_cadence_watch_status.json`. Verified at `2026-07-06T01:54Z`: `next_external_eval_key=quick5k_150M`, `next_external_eval_state=WAITING`, target `150000000`, checkpoint remaining `31,859,570`, live remaining `31,039,039`, and `candidate_count=0`. Eval cadence watcher PID is `25044`; trainer PID `56876` was not restarted.
- `v5_dashboard_watch.py` now forwards the same eval-cadence compatibility aliases to `v5_dashboard_watch_status.json`. Verified at `2026-07-05T21:45Z`: dashboard status has `next_eval_key=quick5k_150M`, `next_stage=quick5k`, `next_target_hands=150000000`, `next_state=WAITING`, and `remaining_checkpoint_hands=41705108`. Dashboard watcher was restarted from PID `48876` to PID `53676`; trainer PID `56876` was not restarted.

- Checked from local status around `2026-07-05T19:02Z`.
- Active run id: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`.
- Trainer PID: `56876`; health watcher `9340`; eval cadence watcher `48356`; dashboard watcher `48876`; checkpoint archive watcher `38004`; audit+hand-review-aware promotion20k watcher `56144`; audit+hand-review-aware formal100k watcher `39752`; extension gate watcher `63576`; extension internal watcher `61936`. The 5100-6000 gate/internal watchers, the 5800 selector-pair watcher, and the 100M quick5k cadence child have completed/exited.
- Latest refreshed status around `19:02Z`: live/checkpoint iter `6326` / `6300`, live/checkpoint hands `103,799,613` / `103,372,987`, health `PASS`, recent h/s about `665.960`. `v5_l6_status_brief.md` / evidence watchdog still report strength unproven.
- Current local gate: latest PASS target `6300`, checkpoint `6300` / `103,372,987`; next gate target is `6400` with ETA about `35m`, and next internal probe target is `6400`.
- Latest official Slumbot evidence is the 100M quick5k cadence run: `5,000` greedy hands, `-85.037 bb/100`, CI lower `-129.224`, L0 only. This is worse than the 75M quick5k point estimate `-71.462 bb/100` and worse than the V4 reference point estimate around `-49.7 bb/100`; it cannot support V4 improvement, L5, or L6.
- Latest completed diagnostic selector pair is 5800: greedy `-115.422 bb/100` over `2,000` hands, CI lower `-211.626`; preflop-callguard `-89.4535 bb/100`, CI lower `-141.603`; callguard-greedy delta `+25.969`. Diagnostic only; not V4/L5/L6 evidence.
- 5800 hand review: greedy artifact audit and hand review `PASS`; callguard artifact audit and hand review `PASS`. Greedy leak shape: SB `-143.2 bb/100`, BB `-87.6`, SB open fold `0.383`, BB vs open call/raise `0.000/0.455`, showdown `-267.3 bb/100 within bucket`, hero_fold `-206.9`. Callguard restored BB call to `0.466` and reduced 3bet to `0.039`, but still scored `-89.453`; SB remained `-118.8`, BB `-60.1`, SB open fold `0.389`, hero_fold `-148.8`. Interpretation: BB call suppression is a real leak, but not sufficient; SB first-action EV and postflop/fold-realization remain major blockers.
- 100M quick5k hand review: artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL` as expected for 5k smoke. Loss shape: SB `-115.0 bb/100`, BB `-55.0`; terminal `hero_fold` `-167.7 bb/100`, `showdown` `-10.6`, `allin_runout` tiny-sample `-5454.5`, `opp_fold` `+348.3`. First preflop decision losses are dominated by `sb_open_c` `-135.2`, `bb_vs_open_lt2.5bb_f` `-100.0`, `sb_open_raise_lt2.5bb` `-181.4`, and `bb_vs_open_lt2.5bb_c` `-81.6`. Rates: SB open fold/call/raise/all-in `0.327/0.506/0.167/0.000`, BB vs open call/raise `0.340/0.088`. Main repeated leaks: SB first-action EV, limp-heavy/under-raised opens, BB/postflop realization, and hero-fold realization. Do not treat this as a simple "force more BB calls" problem.
- Selector-pair artifact audits and hand reviews now exist for all 14 post-cutover selector policy runs from `77M/4700`, `4800`, `5000`, `5100`, `5200`, `5300`, and `5800` for both greedy and preflop-callguard. Official quick5k hand reviews exist for 75M and 100M. Older derived loss reports at `4800` and `77M/4700` were rebuilt from existing dump JSONL to add required SB open call/raise/all-in rates; no Slumbot hands were rerun for that repair.
- `v5_trend_ledger.py` now reads every `slumbot_selector_pair_*_status.json`, connects each policy to CI, artifact audit, and `bench_v55_<tag>_hand_review.json`, and writes a `selector_pair_history` JSON block plus a `Selector Pair Diagnostic History` markdown table. That table should be checked before any training adjustment; the current top repeated leak areas are SB EV, BB EV/defense instability, showdown/postflop value, and SB open behavior.
- `v5_trend_ledger.py` now also writes machine-readable top-level aliases: `overall`, `trend_direction`, `latest_official`, and `decision`. Current top-level trend is `SLUMBOT_POINT_ESTIMATE_DOWN`; `decision.claim_latest_is_better=false` and `decision.promote_strength_claim=false`. Dashboard watcher PID `45960` was restarted after this schema change so future automatic refreshes keep the new fields.
- `v5_slumbot_benchmark_watch.py` now runs the standalone artifact audit and `v5_slumbot_hand_review.py` after each future benchmark; audit failure or missing hand-review data makes the benchmark result `FAIL`. `v5_selector_pair_watch.py` also requires audit PASS and hand-review PASS before reusing existing diagnostic artifacts. `v5_slumbot_benchmark_plan.py` lists audit and hand-review outputs in the planned artifact manifest. `v5_eval_cadence_watch.py` launched the 100M quick5k successfully and should use the same guarded path for the next 150M quick5k.
- Current strength answer: `NOT_PROVEN_STRONGER_THAN_V4`.
- `v5_next_action_queue.md`, `v5_run_dashboard.md`, and `v5_evidence_watchdog.md` were refreshed through the 7000 gate window. Evidence watchdog overall remains `EVIDENCE_ACTIVE_STRENGTH_UNPROVEN`; training health, gate cadence, external eval cadence, Slumbot watchers, eval cadence watcher, latest completed selector-pair diagnostic, and 100M quick5k artifact completeness pass. Strength/latest-better claims remain blocked by insufficient formal Slumbot evidence and the latest quick5k point estimate is down.
- Latest internal probe is 7000 over `200` hands per opponent: verdict `REGRESSION_RISK_INTERNAL`, mean latest `+505.195 bb/100`, delta versus 6800 mean `+515.630`, latest-best remains false for both fixed opponents. The latest checkpoint scored `+4.64 bb/100` vs call-station and `+1005.75 bb/100` vs aggressive, but both CIs still include negative outcomes. This is local fixed-opponent evidence only, not Slumbot strength proof. Next internal target is `7200`.
- 6500 local quality is mixed: gate passed at checkpoint iter `6500` / `106,654,347` hands and health is clean, but the preflop probe remains `WARN` with 4 warnings. The warning shape is greedy argmax call suppression: SB open mean call prob `0.281` with greedy call `0.000`, BB vs min-open mean call prob `0.277` with greedy call `0.000`, BB vs 3bb open mean call prob `0.286` with greedy call `0.000`, and SB vs 3bet mean call prob `0.286` with greedy call `0.000`. Treat this as a selector/policy-shape warning, not a Slumbot strength claim.
- 7000 post-gate review reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, health PASS, internal probe `COMPLETED`, preflop probe `WARN` with 7 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength still `NOT_PROVEN_STRONGER_THAN_V4`. Current queue has advanced to `gate_7100` (`WAITING`, ETA about `37m` at `2026-07-06T00:08Z`), then `internal_probe_7200`.
- Next external evidence: 150M quick5k waiting; saved checkpoint hands are `114,858,660 < 150,000,000`, with about `35,141,340` checkpoint hands remaining. `v5_eval_cadence_watch_status.json` reports `WAITING_FOR_TARGET`, `next_external_eval_key=quick5k_150M`. Promotion20k/formal100k watchers wait for 250M evidence and cannot justify claims yet.
- The 100M quick5k cadence run completed at `2026-07-05T17:49Z` from frozen checkpoint iter `6100` / `100,091,135`. It produced hand JSONL, decision dump JSONL, CI, promotion gate, dump analysis, loss report JSON/MD, artifact audit JSON/MD, hand review JSON/MD, and selector replay JSON/MD. Artifact audit `PASS`; hand review `PASS`.
- 100M saved-checkpoint coverage through 7000 completed. The active extension now uses `v5_gate_sequence_watch.py` PID `7988` for `7100..9200` and `v5_internal_strength_watch.py` PID `42588` for `7200..9200`. This avoids losing local gate/internal evidence while waiting for the 150M and 250M Slumbot targets.
- `v5_l6_status_brief.py` now aggregates all `internal_strength_watch*_status.json` files and direct completed probe outputs, so it reports the completed 7000 internal probe and the pending 7200 extension target instead of stale readiness. Its preflop-intervention section separates reviewed plan target/live/checkpoint from current live/checkpoint, so a reviewed plan is not mistaken for current training state. `v5_evidence_watchdog.py` reports latest internal probe status from the L6 brief, checks freshness against the newest internal watcher status file, and uses dashboard `slumbot_quick5k_latest` so `slumbot_watchers` points at eval-cadence `quick5k_100M` instead of the legacy 75M launcher. `v5_cutover_decision.py` now reports current target `6600`, source artifact `<run_dir>\v5_context_preflop_intervention_plan_6600.json`, decision `HOLD_NO_CUTOVER`, and current live/checkpoint state. `v5_next_action_queue.py` estimates iteration-trigger ETA from live iteration until the target is reached, so future gates do not show stale checkpoint-based ETAs. `v5_run_dashboard.py` also reads internal probe status from watcher `history_tail` and direct `internal_strength_probe_iter*_*.json` files.
- Dashboard watcher is currently PID `39364` after the throughput-audit alias, dashboard status-mirror, speed-decision gate-discovery, and speed-decision alias fixes, so automatic dashboard refreshes preserve top-level training/readiness/internal strength/Slumbot trend/queue fields plus direct `checkpoint_iteration`, `checkpoint_hands`, `recent_hands_per_second`, `next_action_queue_overall`, `next_action_queue_recommendation`, `internal_latest_verdict`, `internal_latest_delta_mean_bb100`, `internal_next_target`, `next_external_eval_key`, `next_external_eval_eta`, `throughput_overall`, `throughput_decision`, `effective_hps`, `speed_decision`, and `speed_effective_hps` fields.
- Checkpoint archive recovery: `v5_checkpoint_archive_watch.py` now shortens archive filenames with a run-id hash to avoid Windows long-path failures while keeping full metadata in the manifest. Checkpoint archive watcher PID `38004` is active; it successfully archived 50M and 100M milestone checkpoints from saved checkpoint iter `6200` / `101,732,149` hands into `<run_dir>\milestone_archives\`, and is now `PENDING` on the 250M milestone.
- Latest non-invasive throughput audit at `2026-07-06T02:18Z`: overall `WARN`, throughput decision `PREPARE_SWEEP_CONTROLLED_RESTART_ONLY`, speed decision `WAIT_FOR_GATE_BEFORE_SPEED_CHANGE`, latest-window effective h/s about `634.7`, and next gate `7400 PENDING`. This confirms collection/inference scheduling is the bottleneck, not PPO/backprop, but any speed intervention must wait for the current gate evidence window.
- Runtime speed tweak at `2026-07-05T18:42Z`: trainer PID `56876` priority was raised from `Normal` to `AboveNormal`, and Windows power plan was changed from `Balanced` to `High performance`. This is a non-model, non-checkpoint throughput tweak. A post-tweak rolling comparison did not show improvement: pre-tweak iter `6228-6286` effective h/s mean `599.0` versus post-tweak iter `6287-6310` effective h/s mean `597.6`; post-tweak inf batch mean was lower (`10.42` vs `11.55`). Keep the tweak if system stability is fine, but do not treat it as sufficient speed optimization.
- A throughput sweep plan exists at `<run_dir>\v5_throughput_sweep_plan.md`, overall `READY_WITH_WARNINGS`, testing workers `24/28/32` and hands-per-iter `16384/32768`. Current speed decision is `WAIT_FOR_GATE_BEFORE_SPEED_CHANGE`: do not execute CUDA sweeps while source trainer PID `56876` is alive or before the current gate evidence window completes; use them only in a reviewed restart/cutover window and compare with `v5_throughput_compare.py`.
- Latest action-prior trend diagnostic at `2026-07-05T21:40Z` is `PASS` with candidate latest iteration `6664` / `109,345,300` hands: preflop call delta `+0.0771`, preflop all-in delta `-0.0338`, postflop raise/all-in delta `+0.0104`, and postflop call delta `-0.0223`. Candidate means over tail 80 were preflop call `0.302`, preflop all-in `0.079`, postflop raise/all-in `0.568`, and postflop call `0.226`. This is training-log action-mix evidence only; it does not override the 100M quick5k L0 result or the 6600 regression-risk internal probe.
- New context-preflop intervention tooling exists but has not been launched. The active review artifact is `<run_dir>\v5_context_preflop_intervention_plan_6600.md`, with 100M hand-log overlay `<run_dir>\v5_100m_intervention_review_6100.md`, overall `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED` / review-required-no-auto-restart.
- `v5_l6_status_brief.md`, `v5_cutover_decision.md`, `v5_evidence_watchdog.md`, `v5_checkpoint_promotion_decision.md`, and `v5_next_action_queue.md` now select the latest context plan, latest completed selector-pair diagnostic, selector-pair hand-review history, and latest official Slumbot quick screen. The cutover decision is `HOLD_NO_CUTOVER`, and the next action queue is `WAITING_FOR_NEXT_TRIGGER` with recommendation to wait for `gate_7400`; next scheduled internal evidence is `internal_probe_7400`.
- `v5_evidence_watchdog.py` now selects the latest `slumbot_selector_pair_*_status.json`; it reports the 5800 selector pair as `PASS` with callguard-greedy delta `+25.969`.
- 5300 local gate completed `PASS`. Preflop probe improved from `WARN` at 5200 to `PASS` at checkpoint `5300` / `86,965,097`; dashboard quality is `SLUMBOT_CANDIDATE_ONLY`. This is a local guardrail improvement only, not Slumbot strength proof.
- 5300 selector-pair diagnostic completed PASS. Status file: `<run_dir>\slumbot_selector_pair_5300_status.md`; frozen checkpoint iter `5300` / `86,965,097`; greedy `-38.9865 bb/100` over `2,000` hands, CI lower `-184.473`; callguard `-34.3855 bb/100`, CI lower `-163.113`; callguard-greedy delta `+4.601`. This is diagnostic-only and cannot support L5/L6 claims.
- 5300 loss shape: greedy BB position improved to `+149.4 bb/100` while SB collapsed to `-227.3`; callguard BB `+27.3`, SB `-96.1`. Both policies still lose heavily at showdown: greedy `-255,374` chips, callguard `-376,304`. Greedy still has low BB vs open call `0.017` and high raise `0.463`; callguard restores BB call `0.740` but only improves the 2k point estimate by `+4.601 bb/100`.
- A 6600 context preflop intervention plan exists at `<run_dir>\v5_context_preflop_intervention_plan_6600.md`, and the 100M hand-log overlay is `<run_dir>\v5_100m_intervention_review_6100.md`. Overall status remains review-required, no automatic restart. The proposed test is still SB-open-focused: keep global preflop prior, add SB-open prior coef `0.03` with target `0.15,0.20,0.63,0.02`, and keep BB-vs-open prior coef `0.0` because 100M evidence does not support a simple "force more BB calls" fix. The completed 7300 review is still no strength proof; the current next action queue recommends waiting for `gate_7400`, with `internal_probe_7400` as the next scheduled internal probe.
- 5200 internal probe completed over `200` hands per opponent. Mean latest `-62.427 bb/100`, delta versus 5000 internal `+327.806`; still `REGRESSION_RISK_INTERNAL` because latest is not best for either fixed opponent and CIs are wide.
- 5400 internal probe completed over `200` hands per opponent. Mean latest `-488.970 bb/100`, delta versus 5200 internal `-426.543`; still `REGRESSION_RISK_INTERNAL`. This is local regression evidence only, not Slumbot strength evidence.
- The 5200 paired selector diagnostic completed PASS at `<run_dir>\slumbot_selector_pair_5200_status.md` from checkpoint `5200` / `85,324,274`. Greedy `-121.054 bb/100` over `2,000` hands, CI lower `-254.009`; callguard `-133.748 bb/100`, CI lower `-236.450`; callguard-greedy delta `-12.694`. Greedy BB vs open call/raise `0.000/0.561`; callguard restored BB call/raise to `0.506/0.112` but scored worse. Treat this as evidence that the current blocker is not a simple "force more BB calls" selector issue.

## Active V5 Evidence Doctrine

The V5-from-zero run is AlphaHoldem-style PPO with Trinal-Clip, 200bb HUNL, 9-slot action space, K-best self-play, and staged Slumbot evaluation. It may deviate from the paper for engineering reasons, but every deviation must be logged and benchmarked.

Current strength baseline:

- V4 reference: about `-49.7 bb/100` over `20.4k` Slumbot hands.
- Paper target: about `+11.1 bb/100`.
- V5 claims are unproven until formal Slumbot CI gates pass.

Milestone levels:

- L1: around `-50 bb/100`, V4/BC anchor neighborhood.
- L2: around `-25 bb/100`.
- L3: around `-10 bb/100`.
- L4: point estimate > 0 but CI may not pass.
- L5: 100k+ Slumbot hands, bb/100 > 0, 95% CI lower > 0.
- L6: near `+11.1 bb/100` with formal evidence.

## Mandatory V5 Training Workflow

This workflow is the default for the AlphaHoldem V5/200bb run:

1. Keep the trainer running at maximum stable throughput unless a documented intervention decision requires a restart.
2. Track training health continuously: iteration, hands, h/s, entropy, value loss, stderr, checkpoint staleness, preflop mix, postflop mix, and watcher state.
3. Evaluate on a schedule while training continues: cheap internal probes, checkpoint gates, Slumbot quick screens, promotion screens, then formal Slumbot screens.
4. Treat every Slumbot benchmark as a hand-review task, not only a score. Preserve hand JSONL and decision dump JSONL, then generate CI, promotion gate, dump analysis, and loss report.
5. Analyze chip loss by position, terminal bucket, street, first preflop decision, top losing line, and hole family before changing training.
6. Compare each result against V4, the previous V5 checkpoints, and the paper target.
7. Change training only when multiple evidence sources agree on a stable leak. A single 2k or 5k result is diagnostic, not enough to tune.
8. Keep official strength evaluation on greedy policy unless the project explicitly changes the policy contract. Guarded/callguard/sample policies are diagnostics unless labeled otherwise.

Reference method: reproduce AlphaHoldem's end-to-end RL idea, but allow pragmatic engineering adjustments such as v55 environment fixes, K-best pool strategy, staged priors, and added diagnostics. Every adjustment must be documented with evidence and a rollback/recheck path.

## Default Agent Operating Loop

When resuming work on this project, first establish the real current state before answering or changing anything:

1. Identify the active run directory, trainer PID, latest checkpoint, iteration, total training hands, health state, h/s, stderr status, and watcher processes.
2. Read the latest status files in the run directory: health, dashboard/status brief, gate status, evidence watchdog, Slumbot watcher status, and selector-pair status.
3. Read the newest Slumbot CI summaries and loss reports under `models/` before making any strength statement.
4. Compare the latest official greedy result against the V4 baseline, previous V5 checkpoints, and the Slumbot target.
5. If a benchmark completed, verify that hand JSONL and decision dump JSONL exist before trusting the score.
6. If there is a leak, update the intervention report or plan before touching training parameters.
7. Answer the user with exact numbers: iteration, hands, h/s, health, benchmark hands, bb/100, CI lower/upper, policy mode, and whether the result is official or diagnostic.

Do not answer "the model is stronger", "training is improving", or "it is close to Slumbot" from intuition. Use Slumbot evidence, internal probes, and loss reports.

Useful progress commands:

```powershell
$run = "C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1"
Get-Content "$run\health_status.md" -TotalCount 160
Get-Content "$run\progress_status.md" -TotalCount 120
Get-Content "$run\v5_l6_status_brief.md" -TotalCount 160
Get-ChildItem "$run\gate_*_status.md" | Sort-Object LastWriteTime -Descending | Select-Object -First 5
Get-Content "$run\gate_5700_status.md" -TotalCount 180
if (Test-Path "$run\gate_5800_status.md") { Get-Content "$run\gate_5800_status.md" -TotalCount 180 }
Get-Content "$run\v5_eval_cadence_watch_status.json" -TotalCount 180
Get-Content "$run\internal_strength_watch_status.json" -TotalCount 180
Get-Content "$run\internal_strength_watch_6200_7000_status.json" -TotalCount 180
Get-Content "$run\v5_preflop_probe_latest.md" -TotalCount 220
Get-Content "$run\v5_checkpoint_delta.md" -TotalCount 180
Get-Content "$run\v5_next_action_queue.md" -TotalCount 180
Get-Content "$run\slumbot_selector_pair_5000_status.md" -TotalCount 180
Get-Content "$run\slumbot_selector_pair_5100_status.md" -TotalCount 180
Get-Content "$run\slumbot_selector_pair_5200_status.md" -TotalCount 180
Get-Content "$run\slumbot_selector_pair_5300_status.md" -TotalCount 180
Get-Content "$run\slumbot_quick5k_100M_cadence_preflight_latest.md" -TotalCount 220
Get-Content "$run\v5_context_preflop_intervention_plan_5300.md" -TotalCount 220
```

Useful process check:

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match 'python|powershell' -and
    ($_.CommandLine -match 'train_v5|v5_selector_pair_watch|play_slumbot|bench_v55_slumbot|v5_dashboard_watch|v5_gate_sequence|v5_health_watch|v5_eval_cadence|v5_internal_strength')
  } |
  Select-Object ProcessId,Name,CreationDate,CommandLine |
  Format-List
```

## Speed Maximization Workflow

The default priority is to keep the trainer running at maximum stable throughput while collecting enough evidence to avoid wasting compute.

Check speed with:

- Training h/s in `health_status.md`.
- Iteration and hand growth over time.
- GPU utilization if needed with `nvidia-smi`.
- Worker count and stale/error state from the trainer stderr/logs.

Current intended high-throughput setup:

- CUDA training.
- `--workers 22`
- `--hands-per-iter 16384`
- `--save-interval 100`
- `--snapshot-every 200`
- `--pool-strategy loss-kbest`
- 200bb v55 environment.

Rules:

- Do not restart the trainer just to inspect status.
- Do not run large Slumbot screens while a critical short diagnostic is already running unless the process list shows capacity.
- If h/s drops materially, inspect stderr, process health, GPU utilization, and watcher contention before changing training.
- Prefer staged watchers over manual ad hoc benchmarks so training can continue unattended.
- Restart a watcher only when it needs updated script code or is stale; avoid interrupting the trainer.

Latest throughput posture:

- Current long-run throughput is acceptable for continuing evidence collection but below paper-scale convenience.
- Last 80 parsed rows averaged `740.075 h/s`, with fast rows `~1180-1348 h/s` at `inf_bs` about `20` and slow rows `~465-525 h/s` at `inf_bs` about `10`.
- A point-in-time GPU check showed `19%` GPU utilization and `4232/12282 MiB` memory use, so the bottleneck is likely collection/batching rather than GPU capacity.
- A later point-in-time resource check showed CPU load about `80%`, GPU utilization `21-29%`, and `4242/12282 MiB` VRAM use. Trainer PID `56876` now runs `AboveNormal`, and the system power plan is `High performance`. No restart was performed.
- Latest throughput audit around `2026-07-06T00:25Z` remains `WARN`: latest-window effective h/s about `663.3`, top-level throughput decision `PREPARE_SWEEP_CONTROLLED_RESTART_ONLY`, and speed decision `WAIT_FOR_GATE_BEFORE_SPEED_CHANGE` because `gate_7100` is still pending. This still points to collection/batching saturation rather than PPO.
- Latest action-prior trend around `2026-07-05T19:06Z` is `PASS`: active tail preflop call mean `0.305` versus parent tail `0.199`, active preflop all-in mean `0.074`, and active postflop RA mean `0.554`. Treat this as a log-shape sanity check only, not Slumbot progress.
- `v5_throughput_sweep_plan.md` is ready with warnings and proposes workers `24/28/32` crossed with hands-per-iter `16384/32768`.
- Do not run those CUDA sweep commands while trainer PID `56876` is alive unless intentionally accepting contention. Use them only in a controlled restart/cutover window and compare candidates with `v5_throughput_compare.py` before changing the main run.

## Strength Answer Protocol

When the user asks how smart the model is, whether it is stronger than V4, or whether it is close to Slumbot, answer using this hierarchy:

1. Formal Slumbot evidence: 100k+ official greedy hands with CI.
2. Promotion evidence: 20k official greedy hands as a candidate signal only.
3. Quick screens: 5k official greedy hands as smoke/regression only.
4. Selector pair diagnostics: greedy vs preflop-callguard for leak localization only.
5. Internal probes/training health: direction and sanity only, never strength proof.

Required comparisons:

- V4 baseline: about `-49.7 bb/100` over `20.4k` Slumbot hands.
- Paper target: about `+11.1 bb/100` vs Slumbot.
- Current official V5 greedy result.
- Current diagnostic policy result, if relevant, clearly labeled non-official.

If the latest V5 official greedy score is worse than V4 or has too few hands, say it plainly. Example conclusion shape:

```text
The current evidence does not prove V5 is stronger than V4. The latest official greedy result is <N> hands, <bb/100> bb/100, CI95 <lower, upper>, which has not passed the 20k/100k evidence gates. A diagnostic callguard result suggests a possible preflop selector leak, but it is not official strength evidence.
```

## Trend and Regression Workflow

When the user asks whether training is going in the right direction or whether each new checkpoint is better, build a scorecard instead of answering from logs alone.

Required inputs:

- Latest health status and h/s.
- Latest local gate and preflop probe.
- Latest internal strength probe and previous internal probe.
- Latest official greedy Slumbot result.
- Latest selector-pair diagnostics and their loss reports.
- V4 baseline and the AlphaHoldem/Slumbot target.

Required answer labels:

- `PROVEN_STRONGER`: only formal Slumbot evidence can support this.
- `CANDIDATE_IMPROVEMENT`: repeated Slumbot or promotion-scale evidence improves but formal gate has not passed.
- `DIAGNOSTIC_IMPROVEMENT_ONLY`: 2k/5k result or selector-pair result improved, but CI/evidence is too small.
- `MIXED`: some local/diagnostic metrics improve while others regress.
- `REGRESSION_RISK`: internal or Slumbot diagnostics worsen and loss reports show structural leaks.
- `NOT_PROVEN_STRONGER_THAN_V4`: default if no sufficient evidence beats the V4 baseline.

Current trend interpretation:

- 4800 greedy selector pair had a positive diagnostic point estimate, but it did not prove strength.
- 5000 regressed in internal probe and selector pair; BB zero-call returned.
- 5100 improved versus 5000 greedy score and BB call frequency, but still lost badly and remained diagnostic only.
- 5200 worsened again and callguard was worse than greedy, showing that simply forcing more BB calls is not enough.
- 5300 improved the 2k diagnostic point estimate to `-38.9865 bb/100` greedy, but CI lower remained very negative and SB/showdown losses persisted.
- 5400 passed the structural gate but local guardrails regressed from preflop probe `PASS` to `WARN`, and the internal fixed-opponent probe regressed to mean `-488.970 bb/100`.
- Therefore the correct current label is `MIXED` plus `REGRESSION_RISK` plus `NOT_PROVEN_STRONGER_THAN_V4`, not "each training step is better."

Whenever a Slumbot result completes, append the new row to the trend comparison and explain whether the change is score improvement, structural improvement, both, or neither. A higher point estimate with worse loss structure is not enough to tune or promote.

The trend comparison must include selector-pair diagnostics, not only official greedy quick screens. `v5_trend_ledger.py` is the canonical aggregator for this: it scans selector status files, joins CI/audit/hand-review artifacts, and records per-policy bb/100, CI lower/upper, SB/BB split, SB-open and BB-facing-open rates, top leak hypotheses, and `training_adjustment`. If a selector policy row is missing audit or hand review, repair the derived artifacts from existing hand/dump JSONL before using that checkpoint for tuning. Do not rerun Slumbot unless the original hand/dump evidence is missing or corrupt.

## Slumbot Hand Review and Training Adjustment Loop

Every Slumbot benchmark must feed back into analysis, not only a score:

1. Confirm `*_hands.jsonl` and `*_dump.jsonl` exist for every benchmark part.
2. Generate CI, promotion gate, dump analysis, and loss report.
3. Read `*_loss_report.md`.
4. Identify whether losses are concentrated by position, street, terminal type, first preflop decision, top losing line, or hole family.
5. Compare those leaks with preflop probes and selector-pair diagnostics.
6. Only then decide whether the next action is continue training, run another diagnostic, change selector, or change training priors.

Do not tune from bb/100 alone. A negative score can be variance, but a repeated structural leak in hand logs is actionable.

Current leak under review:

- The leak shape is checkpoint-dependent. Do not carry a stale conclusion forward without reading the newest loss report.
- At 5000, greedy BB vs open collapsed to `0.000` call rate and callguard improved the diagnostic score sharply.
- At 5100, the exact zero-call BB leak did not repeat: greedy BB vs open call / raise was `0.275` / `0.117`.
- At 5100, the larger visible preflop leak shifted to SB open quality: greedy SB open fold / call / raise / all-in was `0.370` / `0.435` / `0.195` / `0.000`.
- 5100 also still lost heavily through showdown and hero-fold buckets, so preflop alone may not explain the full score.
- At 5200, greedy BB call collapsed back to `0.000`, but callguard scored worse than greedy.
- At 5300, greedy improved to `-38.9865 bb/100` and BB position was positive, but SB collapsed to `-227.3 bb/100`, showdown remained a large loss, and callguard only improved the point estimate by `+4.601 bb/100`.
- At 5400, no new Slumbot hand-log result exists yet, but the local preflop probe regressed to `WARN` and the internal probe was poor against the aggressive fixed opponent. Treat this as a local regression risk to verify with later gates and the 100M Slumbot quick screen.
- At 5600, there is still no new Slumbot hand-log result. The gate passed and the internal fixed-opponent mean improved to `+834.080 bb/100`, but the preflop probe regressed from `4` warnings at 5500 to `5` warnings at 5600 and `v5_checkpoint_delta.md` reports `LOCAL_GUARDRAILS_REGRESSED`. Treat this as mixed local evidence only.
- This indicates unstable selector margins plus SB and postflop/showdown weakness, not a proven strength gain.
- Later checkpoints can change this shape. At 4800, callguard was much worse than greedy; at 5000 it was much better; at 5200 it was worse again; at 5300 it was only slightly better. Never assume callguard is an official improvement.

If a later trained checkpoint still shows greedy BB vs open call near `0.000` and callguard remains much better, treat it as an unresolved selector/preflop-margin problem. If the later checkpoint instead shows SB open fold/call too high and raise too low, do not apply a blanket "more call" preflop prior; prepare a context-conditioned plan that separates SB first action from BB facing an open. Do not silently switch official evaluation from greedy to callguard.

## Slumbot Benchmark Artifacts

Every Slumbot benchmark must preserve hand-level evidence. Treat a benchmark as incomplete if these artifacts are missing:

- `models/bench_v55_<tag>_part*_hands.jsonl`: one row per successful hand with winnings.
- `models/bench_v55_<tag>_part*_dump.jsonl`: one row per decision with hand/action/pot/street context.
- `models/bench_v55_<tag>_ci_summary.json`: exact CI from per-hand JSONL.
- `models/bench_v55_<tag>_promotion_gate.json`: promotion/claim gate result.
- `models/bench_v55_<tag>_dump_analysis.txt`: legacy action/street summary.
- `models/bench_v55_<tag>_loss_report.md` and `.json`: loss-focused report.
- `models/bench_v55_<tag>_artifact_audit.md` and `.json`: non-network artifact completeness audit.
- `models/bench_v55_<tag>_hand_review.md` and `.json`: CI plus loss-structure summary with training-adjustment verdict.

The benchmark runner is:

```powershell
.\scripts\alpha_holdem\bench_v55_slumbot.ps1 `
  -ModelPath <checkpoint.pt> `
  -Tag <tag> `
  -HandsPerSession <n> `
  -Sessions <n> `
  -OutputDir models `
  -RunDir <run_dir> `
  -PolicyMode greedy
```

It writes hand JSONL, decision dump JSONL, CI summary, promotion gate, dump analysis, and loss report. If a future edit breaks any of those outputs, fix the pipeline before trusting the benchmark.

The runner must fail closed on loss-report generation: stale loss report outputs are removed before rebuild, the Python exit code is checked, JSON and markdown outputs are required, and the JSON must include SB open call/raise rates. If any of those checks fail, treat the Slumbot benchmark as incomplete.

The Slumbot benchmark watcher append report should surface the loss report entry points, artifact audit, hand review, and key rates directly: dump analysis path, loss report JSON/MD paths, hand-review JSON/MD paths, SB open fold/call/raise/all-in, BB vs open call/raise, loss report warnings, and top hand-review hypotheses. Use those summary lines first, then open the full loss report and hand review for detail.

`v5_slumbot_benchmark_plan.py` must include artifact-audit and hand-review paths in its artifact manifest. `v5_slumbot_benchmark_watch.py` must run this audit and hand review after a benchmark and include both in the result. A benchmark result is not `PASS` unless the process return code is `0`, the artifact audit is `PASS`, and the hand review is complete. `v5_selector_pair_watch.py` must also require audit `PASS` and hand-review completeness before reusing an existing diagnostic result.

Standalone artifact audit:

```powershell
python scripts\alpha_holdem\v5_slumbot_artifact_audit.py `
  --tag <bench_tag_without_bench_v55_prefix> `
  --output-dir models `
  --expected-parts <parts> `
  --expected-hands <hands> `
  --out-json <run_dir>\slumbot_artifact_audit_<tag>.json `
  --out-md <run_dir>\slumbot_artifact_audit_<tag>.md
```

Use this audit after every Slumbot benchmark and before any strength statement or training intervention. It checks hand JSONL, decision dump JSONL, CI hands, promotion gate, dump analysis, loss report JSON/MD, and required loss-report rates: SB open fold/call/raise/all-in plus BB vs open call/raise. If the audit fails only because an old derived loss report lacks required rates, regenerate the loss report from existing dump JSONL with `v5_slumbot_loss_report.py`; do not rerun Slumbot unless hand/dump evidence is missing or corrupt.

Hand-review summary:

```powershell
python scripts\alpha_holdem\v5_slumbot_hand_review.py `
  --run-dir <run_dir> `
  --output-dir models `
  --tag <bench_tag_without_bench_v55_prefix> `
  --out-json "models\bench_v55_<tag>_hand_review.json" `
  --out-md "models\bench_v55_<tag>_hand_review.md"
```

Use the hand-review `training_adjustment` field before changing training. `SMOKE_ONLY_USE_AS_ONE_SIGNAL` and `DIAGNOSTIC_ONLY_NO_AUTO_TUNE` are not restart approvals. They mean the leak can be tracked, but tuning still needs repeated agreement across Slumbot loss reports, preflop probes, selector diagnostics, and health.

## Loss Analysis Workflow

After any Slumbot result, inspect where chips were lost before changing training:

```powershell
python scripts\alpha_holdem\v5_slumbot_loss_report.py `
  --label <tag> `
  --dumps "models\bench_v55_<tag>_part*_dump.jsonl" `
  --out-json "models\bench_v55_<tag>_loss_report.json" `
  --out-md "models\bench_v55_<tag>_loss_report.md"
```

Read the generated markdown. Focus on:

- Position split: SB vs BB bb/100.
- Terminal buckets: hero fold, opponent fold, showdown, all-in runout.
- Terminal by street.
- First preflop decision buckets.
- Top losing preflop lines.
- Hole-family losses.
- SB open fold, limp/call, raise, and all-in rates.
- BB vs open call and raise rates.

Known current finding from V5 around 72M-75M:

- Official greedy quick5k: about `-122.7 bb/100`.
- Diagnostic preflop-callguard quick2k: about `-53.0 bb/100`.
- Greedy BB vs open had near-zero call rate and excessive 3-bet rate.
- Callguard restored BB call frequency and improved the point estimate, but it is diagnostic only.
- 75M paired diagnostic from frozen checkpoint iter `4600` / `75,479,020` hands confirmed the same leak: greedy `-155.185 bb/100`, callguard `-74.1915 bb/100`, delta `+80.993 bb/100`.
- In that pair, greedy BB vs open call / raise was `0.000` / `0.573`; callguard was `0.423` / `0.154`.

Interpretation: the model has some call probability mass, but greedy argmax can suppress calls and produce a fold/3-bet-heavy preflop strategy. Do not convert callguard diagnostics into official strength claims.

Latest trained-checkpoint finding at 77M/4700 after the controlled preflop-prior intervention:

- Greedy selector pair diagnostic: `-188.911 bb/100` over `2,000` hands, CI lower `-306.110`.
- Preflop-callguard diagnostic: `-147.475 bb/100` over `2,000` hands, CI lower `-255.007`.
- Callguard-greedy delta: `+41.436 bb/100`.
- Greedy BB vs open call / raise improved to `0.221` / `0.177`, so the zero-call leak improved.
- Both policies remain far below V4 and L1. This is not strength improvement evidence.
- The larger current loss shape is postflop/showdown and SB quality: greedy showdown lost `-225,373` chips and all-in runout lost `-280,000` chips; callguard showdown lost `-397,784` chips.

Interpretation: the preflop prior intervention partially improved greedy BB defend frequency, but did not improve external strength. Do not restart again from the 77M 2k result alone. Continue to 4800/internal probe and 100M quick screen unless repeated evidence confirms a new stable leak.

Latest trained-checkpoint finding at 4800 after the controlled preflop-prior intervention:

- Greedy selector pair diagnostic: `+2.0875 bb/100` over `2,000` hands, CI lower `-88.471`, CI upper `92.646`.
- Preflop-callguard diagnostic: `-105.386 bb/100` over `2,000` hands, CI lower `-155.119`, CI upper `-55.653`.
- Callguard-greedy delta: `-107.473 bb/100`; forcing BB calls was harmful at this checkpoint.
- Greedy position split: BB `-41.9 bb/100`, SB `+46.0 bb/100`.
- Greedy terminal buckets improved versus 77M: showdown `+34,681` chips, all-in runout `-20,000` chips, no loss-report warning.
- Greedy BB vs open call / raise was `0.106` / `0.214`, so BB defense remains fold-heavy but no longer has the exact 75M zero-call shape.
- Callguard position split: BB `-139.4 bb/100`, SB `-71.4 bb/100`; showdown lost `-68,710` chips and produced a warning.

Interpretation: 4800 greedy is the first positive Slumbot diagnostic point estimate, but it is only 2k hands and the CI lower bound is negative. It is not proof of V4 improvement, L5, L6, or Slumbot-positive strength. The right next step is to keep training and wait for the staged 100M quick screen and 5000 internal/gate checks. Do not restart from the 4800 2k result alone.

Latest local checkpoint finding at 4900:

- Gate 4900: `PASS` at checkpoint iter `4900` / `80,401,836` hands.
- Health remained `PASS`, entropy about `1.405`, value loss about `3145.9`, pool snapshots `5`.
- Preflop probe remained `WARN`, but the warning shape changed from BB overfold to SB open quality.
- SB open greedy fold / call / raise / all-in: `0.274` / `0.608` / `0.118` / `0.000`, warning for overlimp and underraise.
- BB vs min-open greedy fold / call / raise / all-in: `0.414` / `0.468` / `0.118` / `0.000`.
- BB vs 3bb open greedy fold / call / raise / all-in: `0.324` / `0.459` / `0.217` / `0.000`.
- Delta versus 4800: mean greedy fold `-0.174`, call `+0.336`, raise `-0.162`; warning count stayed `2`.

Interpretation: local BB defense improved by 4900, but SB first-action quality may have degraded toward limp-heavy behavior. This is local guardrail evidence only. Do not restart or promote from 4900 alone; wait for 5000 internal/gate and 100M Slumbot quick screen.

Latest local checkpoint finding at 5000:

- Gate 5000: `PASS` at checkpoint iter `5000` / `82,042,477` hands.
- Health remained `PASS`, entropy `1.3572`, value loss `2700.6792`, pool snapshots `5`.
- Internal probe completed over `200` hands per opponent.
- Latest checkpoint vs call-station: `-879.465 bb/100`, CI lower `-1570.222`.
- Latest checkpoint vs aggressive: `+99.000 bb/100`, CI lower `-636.257`.
- Mean latest internal probe: `-390.233 bb/100`; delta versus the 4800 internal probe: `-449.653 bb/100`.
- Internal verdict: `REGRESSION_RISK_INTERNAL`; dashboard overall: `WORSE_THAN_PREVIOUS_INTERNAL`.

Interpretation: 5000 is a valid and healthy checkpoint, but the cheap internal probe is a regression-risk signal. Internal probes are small and noisy, so do not restart or tune from this alone. A 5000 paired Slumbot selector diagnostic was launched from a frozen iter-5000 checkpoint to check whether the risk appears in real Slumbot hand logs and loss reports.

Latest Slumbot selector-pair finding at 5000:

- Frozen checkpoint: iter `5000` / `82,042,477` hands.
- Greedy selector pair diagnostic: `-156.5635 bb/100` over `2,000` hands, CI lower `-276.175`.
- Preflop-callguard diagnostic: `-17.9765 bb/100` over `2,000` hands, CI lower `-110.054`.
- Callguard-greedy delta: `+138.587 bb/100`.
- Greedy BB vs open call / raise: `0.000` / `0.343`.
- Callguard BB vs open call / raise: `0.540` / `0.026`.
- Greedy SB open fold / call / raise / all-in: `0.519` / `0.000` / `0.481` / `0.000`.
- Callguard SB open fold / call / raise / all-in: `0.521` / `0.000` / `0.479` / `0.000`.
- Greedy position split: BB `-73.1 bb/100`, SB `-240.0 bb/100`.
- Callguard position split: BB `-54.7 bb/100`, SB `+18.7 bb/100`.
- Greedy terminal leaks: all-in runout `-260,000` chips, hero_fold `-232,792`, showdown `-215,639`.
- Callguard still has showdown leak: `-136,674` chips.

Interpretation: the 4800 positive greedy diagnostic did not repeat. The 5000 result confirms a recurrent greedy BB-defense selector/training-shape leak: call probability exists in training, but greedy action selection can still collapse to fold/raise with zero BB calls versus opens. This is strong enough to prepare a reviewed preflop-prior restart plan, but not enough to claim V4 improvement, Slumbot-positive strength, or official callguard promotion.

Latest Slumbot selector-pair finding at 5100:

- Frozen checkpoint: iter `5100` / `83,683,550` hands.
- Greedy selector pair diagnostic: `-116.330 bb/100` over `2,000` hands, CI lower `-196.988`.
- Preflop-callguard diagnostic: `-68.9795 bb/100` over `2,000` hands, CI lower `-132.625`.
- Callguard-greedy delta: `+47.351 bb/100`.
- Greedy BB vs open call / raise: `0.275` / `0.117`.
- Callguard BB vs open call / raise: `0.645` / `0.025`.
- Greedy SB open fold / call / raise / all-in: `0.370` / `0.435` / `0.195` / `0.000`.
- Callguard SB open fold / call / raise / all-in: `0.359` / `0.445` / `0.196` / `0.000`.
- Greedy position split: BB `-93.4 bb/100`, SB `-139.3 bb/100`.
- Callguard position split: BB `+7.0 bb/100`, SB `-144.9 bb/100`.
- Greedy terminal leaks: hero_fold `-218,513` chips, showdown `-192,734`, all-in runout `-80,000`, opponent_fold `+258,587`.
- Callguard terminal leaks: hero_fold `-253,646` chips, showdown `-121,998`, all-in runout `-40,000`, opponent_fold `+277,685`.

Interpretation: the 5100 result does not repeat the 5000 pure BB zero-call failure. BB defense improved, but SB first-action quality is weak and both policies remain far below V4/Slumbot-positive evidence. The next intervention should not be a simple global "more preflop call" target. If tuning is required, prepare a context-conditioned preflop plan that treats SB open and BB facing open separately, and verify whether showdown/postflop losses are the larger blocker.

Latest Slumbot selector-pair finding at 5200:

- Frozen checkpoint: iter `5200` / `85,324,274` hands.
- Greedy selector pair diagnostic: `-121.054 bb/100` over `2,000` hands, CI lower `-254.009`.
- Preflop-callguard diagnostic: `-133.748 bb/100` over `2,000` hands, CI lower `-236.450`.
- Callguard-greedy delta: `-12.694 bb/100`; callguard was worse at this checkpoint.
- Greedy BB vs open call / raise: `0.000` / `0.561`.
- Callguard BB vs open call / raise: `0.506` / `0.112`.
- Greedy SB open fold / call / raise / all-in: `0.099` / `0.001` / `0.900` / `0.000`.
- Callguard SB open fold / call / raise / all-in: `0.126` / `0.001` / `0.873` / `0.000`.
- Greedy position split: BB `-100.0 bb/100`, SB `-142.1 bb/100`.
- Callguard position split: BB `-100.4 bb/100`, SB `-167.1 bb/100`.
- Greedy terminal leaks: hero_fold `-330,954` chips, showdown `-301,417`, all-in runout `-200,000`, opponent_fold `+590,263`.
- Callguard terminal leaks: hero_fold `-296,444` chips, showdown `-278,177`, all-in runout `-140,000`, opponent_fold `+447,125`.

Interpretation: 5200 confirms that greedy can still collapse to zero BB calls versus opens, but callguard no longer improves the score. It restores BB call frequency and reduces some terminal losses, yet loses more overall because opponent-fold gains fall sharply and SB remains very weak. Do not execute a simple "more BB call" or callguard-style intervention from this evidence. The current blocker is broader strategy quality, especially showdown/postflop value and SB open/continuation quality, plus unstable selector margins.

Latest Slumbot selector-pair finding at 5300:

- Frozen checkpoint: iter `5300` / `86,965,097` hands.
- Greedy selector pair diagnostic: `-38.9865 bb/100` over `2,000` hands, CI lower `-184.473`.
- Preflop-callguard diagnostic: `-34.3855 bb/100` over `2,000` hands, CI lower `-163.113`.
- Callguard-greedy delta: `+4.601 bb/100`; callguard was only slightly better and remains diagnostic-only.
- Greedy BB vs open call / raise: `0.017` / `0.463`.
- Callguard BB vs open call / raise: `0.740` / `0.057`.
- Greedy SB open fold / call / raise / all-in: `0.328` / `0.017` / `0.655` / `0.000`.
- Callguard SB open fold / call / raise / all-in: `0.349` / `0.022` / `0.629` / `0.000`.
- Greedy position split: BB `+149.4 bb/100`, SB `-227.3 bb/100`.
- Callguard position split: BB `+27.3 bb/100`, SB `-96.1 bb/100`.
- Greedy terminal buckets: showdown `-255,374` chips, hero_fold `-252,152`, all-in runout `-100,000`, opponent_fold `+529,553`.
- Callguard terminal buckets: showdown `-376,304` chips, hero_fold `-171,473`, all-in runout `-60,000`, opponent_fold `+539,006`.

Interpretation: 5300 is a diagnostic improvement in point estimate versus 5100/5200, but the confidence interval is too wide and formal strength is still unproven. The hand logs say the next review should focus on SB EV, showdown/postflop value, and unstable BB facing-open behavior. Do not promote callguard or restart from this result alone.

Latest local checkpoint finding at 5400:

- Gate 5400: `PASS` at checkpoint iter `5400` / `88,605,809` hands.
- Health remained `PASS`, stderr empty, pool snapshots `5`, environment/action-space lineage unchanged.
- Live health shortly after the gate: iter `5405`, hands `88,687,888`, entropy `1.3288`, value loss `2369.6`, h/s `485`.
- Preflop probe regressed from 5300 `PASS` to 5400 `WARN`; warning delta `+7`; dashboard quality `PREFLOP_GUARDRAIL_WARN`.
- Internal fixed-opponent probe completed over `200` hands per opponent.
- Latest checkpoint versus call-station: `+101.31 bb/100`, CI `+/-189.10`.
- Latest checkpoint versus aggressive: `-1079.25 bb/100`, CI `+/-1381.37`.
- Mean latest internal result: `-488.970 bb/100`; delta versus 5200 internal mean: `-426.543`; latest-best `0/2`; verdict `REGRESSION_RISK_INTERNAL`.
- At the time of the 5400 finding, the next gate/internal target was 5600 and the next external Slumbot quick5k was 100M hands.

Interpretation: 5400 is a valid checkpoint but local quality regressed. This is not enough to restart or make a Slumbot strength claim because it has no new Slumbot hand-log evidence and the internal probe is tiny. Treat 5400 as a regression-risk marker to verify at 5500/5600 and at the staged 100M Slumbot quick screen.

## Selector Pair Diagnostic

Use paired greedy/callguard Slumbot diagnostics only to debug selector leaks. They cannot prove L5/L6.

The paired watcher runs two policies sequentially from one frozen checkpoint:

```powershell
python -X utf8 -u scripts\alpha_holdem\v5_selector_pair_watch.py `
  --run-dir <run_dir> `
  --output-dir models `
  --base-tag <base_tag> `
  --min-training-hands <min_training_hands> `
  --sessions 4 `
  --hands-per-session 500 `
  --sleep-seconds 180 `
  --status-json <run_dir>\slumbot_selector_pair_<target>_status.json `
  --status-md <run_dir>\slumbot_selector_pair_<target>_status.md `
  --log <run_dir>\slumbot_selector_pair_<target>_watch.log
```

Rules:

- Wait for a saved checkpoint. Do not benchmark live unsaved weights.
- The watcher should freeze one checkpoint, run greedy, then run preflop-callguard.
- Compare bb/100 and loss reports for the same checkpoint.
- A large callguard-greedy gap points to selector/preflop margin issues.
- A poor result for both policies points to training strength, not only selector behavior.
- Reusing an existing selector-pair policy result is allowed only when CI JSON, promotion JSON, hand JSONL, decision dump JSONL, loss report JSON/MD, artifact audit, and hand review all pass, and the loss report JSON includes SB open call/raise rates. Otherwise rerun or repair that policy result.

## Evaluation Cadence

Keep staged evidence active:

- Health watcher: continuous training health and staleness.
- Gate watcher: checkpoint validation every 100 iterations.
- Internal strength watcher: cheap checkpoint regression checks.
- Selector pair diagnostic: around 75M/4600 and later staged checkpoints for greedy vs callguard.
- Quick Slumbot screens: quick5k at staged hand targets such as 100M.
- Promotion screen: promotion20k around 250M+ when quality gates allow.
- Formal screen: formal100k only after promotion evidence and quality gates.

For quick5k smoke/regression screens, local quality warnings such as `PREFLOP_GUARDRAIL_WARN` are advisory and must not block launch by themselves. The 100M quick5k already completed; the next quick5k is 150M and should launch once the checkpoint reaches `150,000,000` hands and health/checkpoint checks are clean. Promotion20k/formal100k remain stricter and can require clean quality gates.

Current quick5k cadence status:

- The dedicated `slumbot_quick5k_launch` watcher already completed the 75M post-cutover quick5k and exited. It is not expected to remain as a live process.
- The active backstop for the next quick screen is `v5_eval_cadence_watch.py` PID `47484`.
- `v5_eval_cadence_watch.py` launches due quick5k targets by subprocessing the current `scripts\alpha_holdem\v5_slumbot_benchmark_watch.py`; because the benchmark watcher is audit-aware and hand-review-aware, future quick5k runs should produce `bench_v55_<tag>_artifact_audit.json/md` plus `bench_v55_<tag>_hand_review.json/md`, and fail closed if hand/dump/loss/review artifacts are incomplete.
- `v5_eval_cadence_watch_status.json` may show `candidate_count=0` before 150M because checkpoint hands are still below the next actionable target. That is normal. As of `2026-07-05T22:43Z`, the watcher exposes top-level aliases: `overall`/`state` = `WAITING_FOR_TARGET`, `next_external_eval_key` = `quick5k_150M`, `next_external_eval_state` = `WAITING`, and remaining checkpoint hands about `38,423,012`.
- The 50M quick target is treated as already covered by the existing 75M quick5k CI artifact, and the 100M quick target is complete. The next quick target is 150M, and it should become DUE only when saved checkpoint hands reach `150,000,000`.
- `v5_slumbot_benchmark_plan.py` treats quality warnings as non-blocking for `quick5k`: `PREFLOP_GUARDRAIL_WARN` becomes a PASS detail for smoke benchmarks. Quality warnings are blocking only for `promotion20k` and `formal100k` unless explicitly disabled. Therefore the current preflop WARN should not block the 150M quick5k launch.
- If checkpoint hands are at or above 150M and `v5_eval_cadence_watch_status.json` still shows no `quick5k_150M` launchable candidate, inspect `scripts/alpha_holdem/v5_eval_cadence.py` target detection and existing-CI matching before assuming Slumbot evidence is active.

For `loss-kbest` self-play pools, the current checkpoint does not have to appear in the active pool snapshot. The active pool may prune the current checkpoint in favor of stronger historical opponents. Do not fail a gate solely because the current checkpoint is absent from the active pool when `pool_strategy=loss-kbest`.

Useful status files:

- `<run_dir>\health_status.md`
- `<run_dir>\gate_4600_status.md`
- `<run_dir>\gate_5400_status.md`
- `<run_dir>\slumbot_selector_pair_75M_status.md`
- `<run_dir>\slumbot_selector_pair_77M_status.md`
- `<run_dir>\slumbot_selector_pair_4800_status.md`
- `<run_dir>\slumbot_selector_pair_5000_status.md`
- `<run_dir>\slumbot_selector_pair_5100_status.md`
- `<run_dir>\slumbot_selector_pair_5200_status.md`
- `<run_dir>\slumbot_selector_pair_5300_status.md`
- `<run_dir>\v5_l6_status_brief.md`
- `<run_dir>\v5_evidence_watchdog.md`
- `<run_dir>\v5_cutover_decision.md`
- `<run_dir>\v5_next_action_queue.md`
- `<run_dir>\v5_context_preflop_intervention_plan_5300.md`

Useful process check:

```powershell
Get-CimInstance Win32_Process |
  Where-Object {
    $_.Name -match 'python|powershell' -and
    ($_.CommandLine -match 'train_v5|v5_selector_pair_watch|play_slumbot|bench_v55_slumbot|v5_dashboard_watch|v5_gate_sequence|v5_health_watch|v5_eval_cadence|v5_internal_strength')
  } |
  Select-Object ProcessId,Name,CreationDate,CommandLine |
  Format-List
```

If a Python watcher imports modified scripts, restart that watcher so it loads the new code. Do not restart the trainer unless the intervention decision explicitly calls for it.

Dashboard/watchdog aggregators must not hardcode `slumbot_selector_pair_75M_status.json`; scan `slumbot_selector_pair_*_status.json` and select the latest completed or active diagnostic by checkpoint/frozen hands.

## Training Intervention Rules

Do not tune training from a single noisy 2k or 5k score. Tune only when multiple evidence sources agree:

- Slumbot loss report identifies a stable leak.
- Preflop policy probe agrees with the Slumbot loss shape.
- Selector pair diagnostic confirms whether the leak is selector-specific.
- Training health is otherwise PASS.

Current intervention posture after 5600:

- Keep the active trainer running unless a reviewed intervention decision explicitly requires a restart.
- Keep official Slumbot evaluation greedy.
- Treat the 5000 global preflop-prior plan, 5100 context plan, and 5200 plan as stale for current decisions.
- The active reviewed preflop artifact is still `<run_dir>\v5_context_preflop_intervention_plan_5300.md`, but the current cutover decision is `HOLD_NO_CUTOVER`.
- 5600 passed the lineage/health gate and improved the tiny internal fixed-opponent probe, but local preflop guardrails regressed: preflop probe `WARN`, warning count `5`, and checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`.
- Do not execute the 5300 dry-run restart automatically. It is a reviewed option only if later evidence keeps showing the same SB/context preflop leak.
- Do not restart from the 5400/5500/5600 local evidence alone. It has no new Slumbot hand logs, and internal probes use only `200` hands per opponent with wide CIs.
- Do not apply a blanket "more preflop call" prior when the latest evidence shows SB EV, showdown/postflop losses, and BB facing-open behavior moving in different directions.
- If preflop tuning is required, prefer a context-conditioned plan.
- SB first action context should reduce open-fold/open-limp, raise more often, and keep all-in rare.
- BB facing open context should preserve enough call frequency, avoid fold/3-bet-only collapse, and keep all-in rare.
- Other preflop states should use a conservative fallback target or no extra prior.
- Trainer support exists for context-specific priors via `train_v5.py`:
  `--preflop-sb-open-action-prior-coef/target` and
  `--preflop-bb-vs-open-action-prior-coef/target`.
- When context priors are active, the global preflop prior is applied only to other preflop rows.
- If showdown or postflop terminal buckets dominate the loss report, do not try to fix them only with preflop priors.
- Validate any intervention with preflop probe, selector pair, internal probe, the next Slumbot quick screen, artifact audit, trend-ledger row, and hand-loss review.
- Current default next action as of `2026-07-06T02:23Z`: wait for `gate_7400` and `internal_probe_7400` while keeping the 150M quick5k queued. Live training is `7318` / `120,076,792` hands; saved checkpoint is `7300` / `119,781,345` hands. Use 5400/5500/5600/5700/5800/5900/6000/6100/6200/6300/6400/6500/6600/6700/6800/6900/7000/7100/7200/7300 and the negative 100M quick5k as mixed/regression markers, not automatic restart triggers. The 7300 gate review remains local-only and still cannot support V4/L5/L6 claims.
- As of `2026-07-05T19:14Z`, live training is still healthy at iter `6353` / `104,242,582` hands; `gate_6400` is still pending. The restarted dashboard watcher PID is `54152`.
- `v5_dashboard_watch.py` and `v5_l6_status_brief.py` now expose top-level Slumbot trend fields in their status outputs: latest official hands/bb100/CI lower plus `claim_latest_is_better` and `promote_strength_claim`. Current values remain `5000` hands, `-85.037 bb/100`, CI lower `-129.224`, `False` / `False`, and overall `SLUMBOT_POINT_ESTIMATE_DOWN`.
- As of `2026-07-05T19:21Z`, `v5_post_gate_review.py` is integrated into the dashboard watcher. It writes `<run_dir>\v5_post_gate_review_6400.json/md` and currently reports `PENDING_EVIDENCE`: `gate_6400` is `PENDING`, `internal_probe_6400` is `PENDING`, and the formal Slumbot claim gate is still blocked. The dashboard watcher was reloaded as PID `19348`.
- The post-gate review intentionally remains read-only. It is for evidence consolidation after each local gate, not for auto-restart or strength promotion.
- As of `2026-07-05T19:25Z`, `v5_next_action_queue.py` includes `post_gate_review_6400` directly after `internal_probe_6400`. It currently reports `WAITING`, ETA about `12m`, owner `v5_post_gate_review.py / v5_dashboard_watch.py`, and blocks strength claims until gate/internal/formal Slumbot evidence are ready. Dashboard watcher was reloaded as PID `46408`; trainer PID `56876` was not restarted.
- As of `2026-07-05T19:28Z`, `v5_dashboard_watch.py` refresh order was corrected so `v5_post_gate_review_6400.json/md` is written before `v5_next_action_queue.json/md`. This removes the one-refresh lag where the queue could read the previous post-gate review. Verified same-cycle timestamps at `19:28:04Z`; `post_gate_review_6400` remains `WAITING`, ETA about `9m`, and blocks strength claims. Dashboard watcher was reloaded as PID `4152`; trainer PID `56876` was not restarted.
- As of `2026-07-05T19:31Z`, post-gate target selection was corrected in both dashboard and next-action queue: it now selects the earliest pending gate/internal evidence target, so when `gate_6400` passes before `internal_probe_6400`, the review stays on `6400` instead of jumping to the next gate. `v5_post_gate_review.py` also marks non-scheduled internal probes as `NOT_SCHEDULED` so non-internal gates do not wait forever. Verified `post_gate_review_6400` still `WAITING`, scheduled internal `true`, ETA about `5m`. Dashboard watcher was reloaded as PID `45396`; trainer PID `56876` was not restarted.
- As of `2026-07-05T19:35Z`, `v5_post_gate_review.py` distinguishes `PENDING_EVIDENCE` from `DUE_EVIDENCE_REFRESH`: when live/checkpoint reaches a target but gate/internal watchers have not refreshed yet, next-action queue can mark `post_gate_review_<target>` as actionable `DUE`. It also treats `NOT_SCHEDULED` internal probes as non-blocking. Verified at live iter `6394` / `104,915,368` hands: `post_gate_review_6400` remains `PENDING_EVIDENCE`, readiness flags `gate_live_ready=false`, `gate_checkpoint_ready=false`, `internal_due=false`. Dashboard watcher was reloaded as PID `55748`; trainer PID `56876` was not restarted.
- `gate_6400` passed at checkpoint iter `6400` / `105,013,740` hands. The 6400 internal probe completed over `200` hands per opponent and is a local regression-risk marker: `REGRESSION_RISK_INTERNAL`, mean latest `+47.697 bb/100`, mean lower `-353.203`, delta mean `-649.303`, delta lower `-427.558`, latest-best `0/2`. `v5_post_gate_review_6400.md` now reports `REVIEW_REQUIRED_NO_AUTO_RESTART`; the only hard claim blocker remains formal Slumbot evidence, while watches are local guardrail regression and preflop probe `WARN` with `4` warnings. This is local/internal evidence only, not Slumbot strength proof.
- A fresh 6400 context preflop intervention review was generated at `<run_dir>\v5_context_preflop_intervention_plan_6400.md/json`. It reports `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, but cutover remains `HOLD_NO_CUTOVER`. The plan is read-only and proposes the same reviewed SB-open-focused test shape if explicitly chosen later: keep global preflop prior coef `0.02`, add SB-open prior coef `0.03` target `0.15,0.20,0.63,0.02`, and keep BB-vs-open prior off at coef `0.0`. The 6400 plan confirms action-prior trend `PASS`, lag `1`, preflop probe `WARN`, internal `REGRESSION_RISK_INTERNAL`, and selector pair diagnostic still from 5800. Do not launch this dry-run automatically; next queue recommendation remains waiting for `gate_6500`.
- As of `2026-07-05T19:50Z`, `v5_post_gate_review.py` recommendation text was corrected for gate-only targets. When an internal probe is `NOT_SCHEDULED` for a target, post-gate review and next-action queue must not say to wait for `internal_probe_<target>`. Verified for `post_gate_review_6500`: recommendation is `Wait for gate_6500; no restart or strength claim. No scheduled internal probe for this target.` The queue now tracks `gate_6500` and `post_gate_review_6500` with that same reason, while the next scheduled internal probe remains `internal_probe_6600`. Dashboard watcher was reloaded as PID `53068`; trainer PID `56876` was not restarted.
- As of `2026-07-05T19:55Z`, `v5_next_action_queue.py` also uses a gate-only trigger for non-scheduled internal targets. Verified `post_gate_review_6500` trigger is `gate evidence available for iteration 6500; no internal probe scheduled for this target`, reason remains gate-only, and `internal_probe_6600` is the next internal evidence item. Dashboard watcher was reloaded as PID `50452`; trainer PID `56876` was not restarted.
- As of `2026-07-05T19:58Z`, `v5_l6_status_brief.py` adds backward-compatible top-level aliases `training`, `readiness`, and `internal_strength`. Verified `v5_l6_status_brief.json` reports training live iter/hands `6446` / `105,768,494`, latest gate `6400 PASS`, next gate `6500 PENDING`, latest internal `6400 REGRESSION_RISK_INTERNAL`, next internal `6600 PENDING`, and latest official Slumbot `5000` hands at `-85.037 bb/100` with both claim flags `false`. These aliases are for status-read reliability only; they do not change strength gates.
- As of `2026-07-05T20:02Z`, `v5_dashboard_watch.py` also mirrors key status aliases to the top level of `v5_dashboard_watch_status.json`: `training`, `readiness`, `internal_strength`, `score_progression`, `strength_answer`, gate fields, trend Slumbot fields, claim flags, queue recommendation, and post-gate recommendation. Verified top-level status at live iter/hands `6454` / `105,899,744`, latest gate `6400`, next gate `6500`, latest official Slumbot `5000` hands at `-85.037 bb/100`, claim/promote `false` / `false`. Dashboard watcher was reloaded as PID `55672`; trainer PID `56876` was not restarted.
- As of `2026-07-05T20:05Z`, `v5_dashboard_watch.py` also writes freshness fields to the top level of `v5_dashboard_watch_status.json`: `health_age_seconds`, `latest_gate_age_seconds`, `next_gate_age_seconds`, `run_dashboard_checked_at`, `l6_status_brief_checked_at`, `next_action_queue_checked_at`, and `post_gate_review_checked_at`. Verified at live iter/hands `6460` / `105,998,213`: health age `0.737s`, next gate status age `29.380s`, and queue/post-gate checked_at timestamps are current. Dashboard watcher was reloaded as PID `7536`; trainer PID `56876` was not restarted.
- As of `2026-07-05T20:07Z`, `v5_dashboard_watch.py` mirrors the first next-action queue item to top-level status fields: `next_action_first_key`, `next_action_first_status`, `next_action_first_reason`, `next_action_first_eta`, and `next_action_first_blocks_strength_claim`. Verified top-level status reports `gate_6500`, `WAITING`, ETA `14m`, reason `live iter 6467 < target 6500; remaining 33 iterations.`, blocks strength `true`. Dashboard watcher was reloaded as PID `55300`; trainer PID `56876` was not restarted.
- As of `2026-07-05T20:10Z`, the first next-action mirror also includes `next_action_first_trigger`, `next_action_first_action`, and `next_action_first_owner`. Verified top-level status reports `gate_6500`, trigger `iteration >= 6500 and checkpoint >= 6500`, action `Let gate watcher validate lineage, env/action-space, health, and checkpoint freshness.`, owner `v5_gate_sequence_watch.py`, ETA `12m`, and blocks strength `true`. Dashboard watcher was reloaded as PID `55952`; trainer PID `56876` was not restarted.
- `gate_6500` passed at `2026-07-05T20:23Z` with checkpoint iter `6500` / `106,654,347` hands. `v5_post_gate_review_6500.json/md` now reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, health PASS at live iter `6501`, internal probe is `NOT_SCHEDULED` for 6500, latest internal evidence remains 6400 `REGRESSION_RISK_INTERNAL`, and the hard blocker is still formal Slumbot proof. Local watches remain `LOCAL_GUARDRAILS_MIXED` and preflop probe `WARN` with 4 warnings. This is local evidence only, not V4/L5/L6 proof.
- As of `2026-07-05T20:26Z`, `v5_dashboard_watch.py` and `v5_next_action_queue.py` were patched so a newly passed gate whose post-gate review is missing or still `PENDING_EVIDENCE`/`DUE_EVIDENCE_REFRESH` is refreshed before the dashboard advances to the next target. This prevents gate-only checkpoints like 6500 from being skipped after PASS. The 6500 review is already finalized, so the current next target can move to 6600. Dashboard watcher was reloaded as PID `49052`; trainer PID `56876` was not restarted.
- As of `2026-07-05T20:33Z`, live training is healthy at iter `6522` / `107,015,237` hands, checkpoint iter `6500` / `106,654,347`, dashboard watcher PID `49052`, trainer PID `56876`. `v5_context_preflop_intervention_plan_6500.json/md` is the latest reviewed context-preflop plan and reports `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, not an automatic restart: action-prior trend `PASS` with latest iter `6515`, preflop probe `WARN`, internal evidence still latest 6400 `REGRESSION_RISK_INTERNAL`, selector-pair evidence still diagnostic-only from 5800, greedy BB-vs-open call/raise `0.000` / `0.455`, and greedy SB-open fold/call/raise/all-in `0.383` / `0.005` / `0.612` / `0.000`. The current queue first action is `gate_6600` (`WAITING`, ETA about `35m`), then `internal_probe_6600`, then `post_gate_review_6600`. Do not launch the 6500 dry-run command automatically; it is a reviewed option only if fresh 6600 evidence or Slumbot hand logs justify intervention.
- As of `2026-07-05T20:38Z`, `v5_eval_cadence_watch.py` was patched and restarted as PID `48356` so its status JSON mirrors the next external eval at top level. Verified status: `WAITING_FOR_TARGET`, checkpoint hands `106,654,347`, current hands `107,212,159`, `next_external_eval_key=quick5k_150M`, target `150,000,000`, ETA about `16h 58m`, completed keys `quick5k_100M`. Trainer PID `56876` was not restarted.
- As of `2026-07-05T20:47Z`, `v5_cutover_decision.py` now writes a nested `intervention` alias plus `intervention_source`, and `v5_dashboard_watch.py` mirrors cutover fields to top-level status. Verified dashboard watcher PID `49392` reports `cutover_decision=HOLD_NO_CUTOVER`, `cutover_target=6500`, `cutover_intervention_overall=CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, `cutover_intervention_target=6500`, and source `<run_dir>\v5_context_preflop_intervention_plan_6500.json`. Trainer PID `56876` was not restarted.
- As of `2026-07-05T20:50Z`, `v5_gate_watch.py` now writes top-level gate aliases: `live_iteration`, `live_hands`, `checkpoint_iteration`, `checkpoint_hands`, `live_reached_target`, `checkpoint_reached_target`, `remaining_live_iterations`, and `remaining_checkpoint_iterations`. `gate_6600_status.json` was refreshed and reports `PENDING`, live iter/hands `6559` / `107,622,272`, checkpoint iter/hands `6500` / `106,654,347`, remaining live iterations `41`, remaining checkpoint iterations `100`, health `PASS`. Gate sequence watcher was restarted from PID `55848` to PID `63576`, starting at `6600` to avoid re-appending previous PASS gates. Trainer PID `56876` was not restarted.
- As of `2026-07-05T20:53Z`, `v5_post_gate_review.py` mirrors gate/internal readiness to top-level review fields: `gate_overall`, `gate_live_iteration`, `gate_checkpoint_iteration`, `gate_remaining_live_iterations`, `gate_remaining_checkpoint_iterations`, `internal_probe_state`, `internal_probe_scheduled`, and `strength_answer`. Verified `v5_post_gate_review_6600.json` reports `PENDING_EVIDENCE`, gate live/checkpoint `6566` / `6500`, remaining live/checkpoint iterations `34` / `100`, internal probe `PENDING`, scheduled `true`, and `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard watcher was restarted from PID `49392` to PID `20888`; trainer PID `56876` was not restarted.
- As of `2026-07-05T21:01Z`, `v5_dashboard_watch.py` status payload also mirrors direct checkpoint and queue aliases: `checkpoint_iteration`, `checkpoint_hands`, `recent_hands_per_second`, `next_action_queue_overall`, and `next_action_queue_recommendation`. Verified top-level status reports live iter/hands `6584` / `108,032,431`, checkpoint iter/hands `6500` / `106,654,347`, health `PASS`, `next_action_queue_overall=WAITING_FOR_NEXT_TRIGGER`, recommendation `Wait for gate_6600`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard watcher was restarted from PID `20888` to PID `30032`; trainer PID `56876` was not restarted.
- As of `2026-07-05T21:13Z`, `gate_6600` passed at checkpoint iter `6600` / `108,294,892`, and `internal_strength_probe_iter6600_200h.json/md` completed. `v5_post_gate_review_6600.json/md` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal `COMPLETED`, internal verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-436.917` / `-872.760`, preflop probe `WARN` with 3 warnings, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard/queue advanced to `gate_6700`; next scheduled internal probe is `6800`. Trainer PID `56876` was not restarted.
- As of `2026-07-05T21:19Z`, `v5_action_prior_trend.json/md` was refreshed to candidate latest iter `6620` and remains `PASS`. `v5_context_preflop_intervention_plan_6600.json/md` was generated as review-only; it reports `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, action-prior trend lag `1`, internal `REGRESSION_RISK_INTERNAL`, preflop probe `WARN`, planned SB-open prior coef `0.03`, planned BB-vs-open coef `0.0`, and a dry-run command for `_after6600_ctxreview_r1` that was not executed. Dashboard/cutover now points at the 6600 plan with `HOLD_NO_CUTOVER`; trainer PID `56876` was not restarted.
- As of `2026-07-05T21:24Z`, `v5_dashboard_watch.py` also mirrors internal and external-eval aliases to top-level status: `internal_latest_iteration`, `internal_latest_hands`, `internal_latest_verdict`, `internal_latest_delta_mean_bb100`, `internal_latest_delta_lower_bb100`, `internal_next_target`, `internal_next_state`, `next_external_eval_key`, `next_external_eval_stage`, `next_external_eval_target_hands`, `next_external_eval_state`, `next_external_eval_eta`, `next_external_eval_checkpoint_hands`, and `next_external_eval_remaining_checkpoint_hands`. Verified status reports internal latest `6600 REGRESSION_RISK_INTERNAL`, next internal `6800`, next external `quick5k_150M` waiting with ETA about `15h 39m`. Dashboard watcher was restarted from PID `30032` to PID `48876`; trainer PID `56876` was not restarted.
- As of `2026-07-05T21:57Z`, `gate_6700` passed at checkpoint iter `6700` / `109,936,130` hands with health `PASS`. A one-shot dashboard refresh wrote `v5_post_gate_review_6700.json/md`, which reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED` for 6700, latest internal evidence still 6600 `REGRESSION_RISK_INTERNAL`, preflop probe `WARN` with 3 warnings, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard/queue advanced to `gate_6800` (`WAITING`, ETA about `46m`) and `internal_probe_6800`; the next external Slumbot screen remains `quick5k_150M`, waiting on checkpoint hands `150,000,000` with `40,063,870` checkpoint hands remaining. Trainer PID `56876` was not restarted.
- As of `2026-07-05T22:43Z`, `gate_6800` passed at checkpoint iter `6800` / `111,576,988` hands, and `internal_strength_probe_iter6800_200h.json/md` completed. `v5_post_gate_review_6800.json/md` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal `COMPLETED`, internal verdict still `REGRESSION_RISK_INTERNAL`, latest mean `-10.435 bb/100`, delta versus 6600 mean `+378.785`, preflop probe `WARN`, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard/queue advanced to `gate_6900`; next scheduled internal probe is `7000`. The next external Slumbot screen remains `quick5k_150M`, waiting on checkpoint hands `150,000,000` with `38,423,012` checkpoint hands remaining. Trainer PID `56876` was not restarted.
- As of `2026-07-05T23:22Z`, `gate_6900` passed at checkpoint iter `6900` / `113,217,727` hands with health `PASS`. A one-shot dashboard refresh wrote `v5_post_gate_review_6900.json/md`, which reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal probe `NOT_SCHEDULED` for 6900, latest internal evidence still 6800 `REGRESSION_RISK_INTERNAL`, preflop probe `WARN`, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard/queue advanced to `gate_7000` (`WAITING`, ETA about `39m`) and `internal_probe_7000`; the next external Slumbot screen remains `quick5k_150M`, waiting on checkpoint hands `150,000,000` with `36,782,273` checkpoint hands remaining. Trainer PID `56876` was not restarted.
- As of `2026-07-06T00:08Z`, `gate_7000` passed at checkpoint iter `7000` / `114,858,660` hands with health `PASS`, and `internal_strength_probe_iter7000_200h.json/md` completed. `v5_post_gate_review_7000.json/md` reports `REVIEW_REQUIRED_NO_AUTO_RESTART`: gate PASS, internal `COMPLETED`, internal verdict still `REGRESSION_RISK_INTERNAL`, latest mean `+505.195 bb/100`, delta versus 6800 mean `+515.630`, preflop probe `WARN` with 7 warnings, checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`, and strength `NOT_PROVEN_STRONGER_THAN_V4`. Dashboard/queue advanced to `gate_7100`; next scheduled internal probe is `7200`. The next external Slumbot screen remains `quick5k_150M`, waiting on checkpoint hands `150,000,000` with about `35,141,340` checkpoint hands remaining. Gate watcher PID `7988` now covers `7100..9200`; internal watcher PID `42588` covers `7200..9200`. Trainer PID `56876` was not restarted.

Do not overfit Slumbot. The agent must remain a general 200bb HUNL player and should keep single-forward-pass decision latency.

## Controlled Preflop Intervention

The 75M selector pair confirmed a greedy BB-defense leak, so a reviewed intervention run was launched:

- Source run: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1`
- Source checkpoint: iter `4600`, hands `75,479,020`
- New run: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- Change: `preflop-action-prior-coef 0.02`, target `0.24,0.36,0.38,0.02`
- Unchanged: 200bb v55 environment, Trinal-Clip PPO, K-best `loss-kbest`, official Slumbot evaluation remains `greedy`

The immediate post-cutover quick5k at iter `4600` / `75,479,020` hands is a cutover baseline, not proof that the intervention worked. It froze the initial resume checkpoint before meaningful training under the new prior. It scored `-71.462 bb/100` over `5,000` hands, but the loss report still showed greedy BB vs open call / raise `0.000` / `0.574`.

The first trained checkpoint check was the 77M selector pair at iter `4700` / `77,119,719` hands. It showed greedy BB vs open call / raise improved to `0.221` / `0.177`, but strength got worse: greedy `-188.911 bb/100`, callguard `-147.475 bb/100`, delta `+41.436`. Treat this as partial preflop-shape improvement and failed strength evidence. The next focus is whether later checkpoints reduce postflop/showdown and SB losses while keeping sane BB defend frequency.

The next trained checkpoint check was the 4800 selector pair at iter `4800` / `78,760,653` hands. Greedy scored `+2.0875 bb/100` over `2,000` hands with CI lower `-88.471`; callguard scored `-105.386 bb/100` with CI lower `-155.119`. This is a useful positive diagnostic signal for greedy but not a claim. It also proves callguard should not be used as the official policy, because it can over-force calls and lose much more than greedy. Continue training toward the 100M Slumbot quick screen before making another training intervention.

The 4900 local gate passed at iter `4900` / `80,401,836` hands. It did not include a Slumbot score. The local preflop probe stayed `WARN`: BB defend call frequency improved, while SB open became limp-heavy and under-raised. Treat this as mixed local evidence. The Slumbot loss report now records SB open fold / limp-call / raise / all-in rates, not just SB open fold rate; use that field to verify whether the 4900 local SB warning appears in real Slumbot hand logs.

The 5000 local gate passed at iter `5000` / `82,042,477` hands. It did not prove strength. The 5000 internal probe was worse than 4800: mean latest `-390.233 bb/100` over the two tiny internal opponents, delta `-449.653 bb/100` versus the previous internal probe, verdict `REGRESSION_RISK_INTERNAL`. Treat this as a risk flag only. The correct response is to inspect the frozen 5000 Slumbot selector-pair hand logs and loss reports before changing training.

The 5000 frozen Slumbot selector pair is now complete. Greedy scored `-156.5635 bb/100` over `2,000` hands, while preflop-callguard scored `-17.9765 bb/100`; the delta is `+138.587 bb/100`. Greedy BB vs open call / raise was `0.000` / `0.343`, while callguard restored BB calls to `0.540`. This confirms the preflop selector/training-shape leak at 5000. A reviewed intervention plan exists at `<run_dir>\v5_preflop_intervention_plan.md` with overall `PREFLOP_INTERVENTION_REVIEW_REQUIRED`, proposed preflop prior coef `0.03`, and target `0.20,0.46,0.32,0.02`. Do not execute the restart automatically; either wait for the 100M quick screen or explicitly choose to test the reviewed restart from 5000.

The 5100 frozen Slumbot selector pair is now complete. Greedy scored `-116.330 bb/100` over `2,000` hands, while preflop-callguard scored `-68.9795 bb/100`; the delta is `+47.351 bb/100`. Greedy BB vs open call / raise recovered to `0.275` / `0.117`, so the exact 5000 zero-call BB leak did not repeat. The main visible preflop weakness shifted to SB open fold/call/raise/all-in `0.370` / `0.435` / `0.195` / `0.000`, plus continuing showdown/hero-fold losses.

The 5000 global-prior intervention plan, the 5100 context-preflop plan, and the 5200 plan must be treated as stale after the 5300 selector pair and 5300 context review. The 5300 evidence improved the diagnostic point estimate, but the loss shape still points to SB EV, showdown/postflop value, and unstable BB facing-open behavior. Context-conditioned preflop-prior support exists for future restarts, but no restart has been launched from it.

The latest completed reviewed plan is `<run_dir>\v5_context_preflop_intervention_plan_6600.md`, with the 100M hand-log overlay still at `<run_dir>\v5_100m_intervention_review_6100.md`. It reports context-preflop review required but no auto-restart; dashboard/cutover decision remains `HOLD_NO_CUTOVER`. After the completed 8600 gate/internal review, the next action queue waits for `gate_8700`, the next scheduled internal probe is `internal_probe_8800`, and the next external Slumbot smoke is still 150M quick5k. Do not launch a restart from 5300, 5400, 5500, 5600, 5700, 5800, 5900, 6000, 6100, 6200, 6300, 6400, 6500, 6600, 6700, 6800, 6900, 7000, 7100, 7200, 7300, 7400, 7500, 7600, 7700, 7800, 7900, 8000, 8100, 8200, 8300, 8400, 8500, or 8600 unless explicitly choosing to test a reviewed intervention after reading fresh gate, internal probe, Slumbot hand logs, loss report, selector trend-ledger row, artifact audit, and hand review. The 8600 preflop guardrail remains WARN and Slumbot strength is still unproven, so continue evidence collection rather than automatic restart.

Before any similar restart, generate and read a plan:

```powershell
python scripts\alpha_holdem\v5_preflop_intervention_plan.py `
  --run-dir <run_dir> `
  --target-iteration <saved_checkpoint_iteration> `
  --preflop-action-prior-coef 0.02 `
  --preflop-action-prior-target 0.24,0.36,0.38,0.02 `
  --out-json <run_dir>\v5_preflop_intervention_selectorpair75M_plan.json `
  --out-md <run_dir>\v5_preflop_intervention_selectorpair75M_plan.md
```

The command above is the historical global-prior planner shape. After the 5300 result, do not execute a new global-prior restart from this template unless the newest evidence again shows one consistent global preflop leak. If SB open and BB defense point in different directions, use a context-conditioned planner first.

Only proceed if the plan reports `PREFLOP_INTERVENTION_REVIEW_REQUIRED`, `CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED`, or a stricter reviewed restart recommendation, and the evidence shows:

- Selector pair state `PASS`.
- A repeated structural leak in hand logs, not only a worse score.
- The preflop probe and selector-pair loss reports agree on the leak shape.
- The proposed intervention targets that leak without silently changing the official greedy policy.
- The restart is documented as a targeted training intervention, not a strength claim.

## Claim Rules

Never say "stronger than V4", "beats Slumbot", L5, or L6 unless the evidence supports the exact claim.

Allowed statements:

- Training health is PASS.
- A diagnostic result suggests a possible selector leak.
- A quick5k result is an external smoke/regression screen.
- A promotion20k result can support candidate promotion but cannot prove L5/L6.

Not allowed:

- Using 2k or 5k as proof of improvement.
- Using callguard/guarded/sample policy as official greedy strength unless explicitly labeled diagnostic.
- Claiming formal success without 100k+ hands and positive CI lower bound.

When in doubt, report exact hands, bb/100, CI lower, policy mode, and whether the result is official or diagnostic.
