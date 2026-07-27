# Archived CardPilot Agent Workflow

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

Current authoritative update (2026-07-23 04:13 EDT): RS009 direct materialization is
terminal implementation-audit PASS and one-qualification-ready. Runner/result-auditor/
launcher/implementation-auditor SHAs are
8c764d35c1fe5eefd28bcf2173c1181504b8b33242d8d50d8d89a43acb97780f /
10c7f8b4912bdcb956880889c35f137f460aac62797e7e79909f2cb17a36cc48 /
120e9bad1df9fcee366bc168f7819e918beb5359c48bae487b0ee01559fa5044 /
acd88f66c9aec376282552d45ec8bc953f7c1714c2de7332df3b824d77ef2ae5.
Implementation-audit SHA
f6bee04df309a6067af693da1712848585376f4014e69ee21f292890476a3729
PASS32/32 binds all29 registered inputs/runtime/checkpoint assets,proves complete
normalized runner and result-auditor AST equality to RS007,and finds forbidden
runtime indirection/sys.modules writes0. The sole final-launcher ContractProbe nonce
RS009_FINAL_IMPORT_PROBE_2034972301 exited0 with exact RS009 identity,CUDA0 child
contract,torch absent,files_written0 and identical before/after token snapshots.
This directly proves module import and dataclass decoration without the terminal
RS007C1 bridge. The inherited RS007C1 deep test was not rerun and has no strength
authority. Qualification/quick5k roots remain absent;model loads,resolution rows,
network,Slumbot and official hands0. Snapshot/ledger SHAs
471ff0de5608d459574f3c4f7c93b58e3761780d6e117d941e01f24c45f085ed /
2e10b5deb1fa1e3f771f999087cf1b661d6039ba0b0a2c26c08e1010ad6d9749.
Latest formal H11 remains -100.2475bb/100 CI95[-112.4067,-88.0883],last quick5k
-146.1726;behavior0;L0;route exhaustion false;goal ACTIVE. Next only is exactly one
qualification through the frozen launcher with nonce RS009_QUALIFICATION_2036972301
and implementation-audit SHA above,then exactly one frozen result audit and exact
judgment;stop before quick5k. Do not alter code or run another probe.

The 2026-07-23 03:54 update below is historical.

Current authoritative update (2026-07-23 03:54 EDT): RS008 is terminal
`RS008_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_EMBEDDED_SIZE_GATE`.
Failure/audit SHAs
6af981b4b1ff439fe8862aa618d6102a9679a5999e2d532f27f7f784782cd147 /
8705cbee2e304f890f8bdc690c9e67d4a813a2caa6a6617ddebf211ebbbf31f8
PASS35/35 prove the registered full-AST contract was unsatisfiable:RS008 prereg/audit
are17,815/6,844 bytes,but immutable parent `verify_frozen_inputs` embeds21,218/9,251
inside the function;unchanged code must reject,while changing them violates the
top-level-only change set. No RS008 code,probe,qualification row,rollout,GPU load or
hand existed;never implement,repair or reclassify it. WS009 review selected
`RS009_DIRECT_MATERIALIZED_CONTROL_SIZE_CONSTANTS`. Fresh RS009 identity/token are
72e9bb6b8a4f4618aa6657710b66c5c91918b64faadbbf63e0655554688c80c4 /
72e9bb6b8a4f4618aa6657710b66c5c9;preregistration/audit SHAs
54b081b37171449d782b6b64ffaf84e9c553eea2c0bae426a00533790d229aea /
4d22631cdb6d58d8a4a3d543daf4fe30f0aa9ea474214af4336e7796963465c6
PASS95/95 establish
`RS009_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY`.
RS009 adds only top-level PREREG_BYTES/PREREG_AUDIT_BYTES and replaces exactly the
two parent literals in verify_frozen_inputs;all other full runner AST and result-
auditor AST must normalize bit-exact to RS007. An in-memory no-write simulation
observed exactly2 replacements and full normalized equality,proving satisfiability.
Runtime importlib/runpy/exec/eval/wrapper/monkeypatch/sys.modules mutation remain
forbidden. Future implementation audit owns one final-launcher zero-file probe nonce
RS009_FINAL_IMPORT_PROBE_2034972301;only PASS authorizes one qualification nonce
RS009_QUALIFICATION_2036972301. Full qualification/result-audit PASS then requires
quick5k4x1250 at >-126.1726bb/100 plus all resolver/aggression/evidence gates.
Snapshot/ledger SHAs
df83254daa569a683a7e2f3626c2774b2eae384d4e95525a65269ae57bb8fd25 /
da9d62fd539b6a8794a64c02c3851d61880dc345c25f8a993e24303b351a5d49.
No RS009 code,probe,qualification,GPU,network,Slumbot or official hands ran;latest
formal H11 remains -100.2475bb/100 CI95[-112.4067,-88.0883],last quick5k -146.1726;
behavior0;L0;route exhaustion false;goal ACTIVE. Next only is materialize four RS009
files,full normalized-AST audit,one final-launcher zero-file probe,implementation
audit,and stop qualification-ready.

The 2026-07-23 03:21 update below is historical.

Current authoritative update (2026-07-23 03:21 EDT): RS008 direct-materialized
zero-indirection runner identity/token are
a414670d98ae3502864ab17800925e2c83ea2af95f7925514262d64251332f6c /
a414670d98ae3502864ab17800925e2c. Preregistration/audit SHAs
71f510620d9df7ed24bd5b46f31928561d4d2cda38f2015e64943e3d73114c37 /
64d25b56d6643adb5177805a106595c4234137f0730ff8123493c847756324c6
PASS80/80 establish
`RS008_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_READY_ONLY`.
The audit rehashed22 science and10 control-lineage inputs,recomputed identity and
proved all implementation/output paths absent. Future runner/result-auditor must be
fully materialized source,not runtime descendants. After sentinel-normalizing only
the registered top-level identity/path constants,their complete AST dumps must equal
immutable RS007 parents. Runtime importlib,runpy,exec,eval,wrapper,monkeypatch and
sys.modules mutation are forbidden;the inherited read-only sys.modules torch-presence
probe is permitted. The implementation auditor owns exactly one final-launcher
ContractProbe nonce RS008_FINAL_IMPORT_PROBE_2034972300 proving direct import,
dataclass decoration,exact child environment,frozen inputs,torch absent and files0.
Do not rerun the inherited RS007C1 deep selftest or use it as strength evidence.
Only an implementation-audit PASS may authorize one qualification nonce
RS008_QUALIFICATION_2036972300 with all RS007 science/MC32/resource/checkpoint gates
bit-exact. A full qualification/result-audit PASS must next run greedy-direct4x1250
quick5k and exceed -126.1726bb/100 plus resolver/fallback/aggression/evidence gates.
Snapshot/ledger SHAs
08c05bb45e2fec28658a92bd8ca8e4be9ee56e592ecb5883e028ad90a7bdedbe /
75ceea224b816117ba54b328baccab417f3b531d725f53c76c801691f8cfe810.
No RS008 code,probe,
qualification,GPU/model,quick5k,network,Slumbot or official hand ran;behavior0;latest
formal H11 -100.2475bb/100 CI95[-112.4067,-88.0883],last quick5k -146.1726;L0;
route exhaustion false;goal ACTIVE. Next only is materialize four RS008 files,static
full-AST audit,one final-launcher zero-file probe,implementation audit,and stop
qualification-ready. Do not qualify or quick5k automatically this boundary.

The 2026-07-23 02:52 update below is historical.

Current authoritative update (2026-07-23 02:52 EDT): RS007 science implementation
passed after one terminal prechild checker defect and its sole goal-permitted fresh
RS007C1 correction. Parent implementation-audit failure/audit SHAs
775ca45d51f916e83e4ab54eb3d8fd76197e33bdc2ae7a89d9e4fecba65ecfee /
410b735c6f6a63b84e24573d91bcca330285576cb3c2a2531de00fdb0323030c
localize quote-sensitive AST-unparse matching before any child. RS007C1 corrected
identity ac09e2283fc6459f887b83e1d1e22b6d1375d5d03339a8a41d73225f1e344129
then passed implementation audit SHA
bccb55981fd8bcce4388c73b5fbee200385dd9d6b8f25f961652be494b0a2804
PASS26/26:the one deep test replayed29,878 source actions,4,096 boundary rows,1,280
terminal rows and8,192 comparator deals;both exact launcher probes passed with zero
file diff. However the one RS007C1 qualification launcher attempt exited1 before
parent import,child contract,output root,GPU/model or any science row because its
dynamic-import bridge omitted sys.modules registration required by dataclasses.
Failure/audit SHAs
648838f7a05109dbade1e40b76b0bc958a169edef3b9d8bae2976e4f9d4549a7 /
0d2513f64b2f647eb50f5fa89e8a3d0255adf73b76640ae5201ef6e1ae4664d5
PASS24/24 establish
`RS007C1_QUALIFICATION_BRIDGE_PREOUTPUT_DYNAMIC_IMPORT_MODULE_REGISTRATION_FAILURE`.
Never repair,rerun or reclassify either terminal identity. Qualification science
rows/interfaces/resolutions/rollouts/model-loads are0;network,Slumbot and official
hands0. The repeated-control simplification WS008 identity
3e7b395db8def26a3646f294e79c6122f88d82662ffbf33dbf2b69946d73164c
preregistered/audited and selected/audited
`RS008_DIRECT_MATERIALIZED_RUNNER`:one fresh directly executable runner must be
normalized-AST identical to RS007 except identity/authority paths,with no importlib,
runpy,wrapper,monkeypatch or runtime indirection;one zero-file import/dataclass smoke
must traverse the final launcher before one qualification. Inherit the RS007C1 deep
test as implementation evidence only;do not rerun it or infer strength. Route-review
artifacts are reporting-only;RS008 implementation has not begun. Latest formal H11
remains -100.2475bb/100 CI95[-112.4067,-88.0883],last quick5k -146.1726;behavior
windows0;L0;all four non-V6 families remain;route exhaustion false;goal ACTIVE.
Next only is separate RS008 preregistration and preimplementation audit;no code,
qualification,quick5k,training,checkpoint,network or official hands automatically.

The 2026-07-23 01:24 update below is historical.

Current authoritative update (2026-07-23 01:24 EDT): fresh RS007 identity/token are
bf43f304c4709f356af131d60ef6e35a52a7456d215987abce8180419c4ed6d0 /
bf43f304c4709f356af131d60ef6e35a. A read-only four-dump census/audit SHAs
1e8dcf9488c287d5409dac9ad8304ebd835c1a6ce70e590b42e1d53ce1d5810a /
82ff469aad769e6e61cf88270d8472844a95b711c4ef5258169f7354ed9b73fb
PASS31/31 prove the domain boundary is material:of29,878 actions,all12,564 hero
actions are exact policy slots,but1,658/17,314 opponent actions are poker-legal
bet/raise targets outside the table(852/442/196/168 by street);basic illegal0 and
projection0. Preregistration/audit SHAs
0b881b6b5651a23dea03f625cb0e8d4880752e5286f7f2cd145eda46980beeeb /
aa0f6582ac80a814f7d116a736d245440121ddcf1cc46b126a0adf67adff7a97
PASS167/167 establish
`RS007_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.
The fresh-from-scratch dual-domain state freezes `apply_public_increment` for every
exact-cent poker-legal raw action without policy lookup,and `apply_policy_slot` for
one-to-one nonnull public-legal H11 slots only. External projection/drop/collision/
renormalization and RS005/RS006 import/copy/wrapper/monkeypatch are forbidden. Exact
legality covers blinds/BB option,full minimum bet/raise,short all-in,reopen and no-
reopen rights,opponent-all-in no-raise,street closure,chance and terminal payout.
Qualification gates29,878 rows,24,878 adjacent transitions,1,658 external exact,
12,564 dual-path hero actions,4,096 balanced rule-boundary rows,6,921 live interfaces,
1,280 terminal rows,8,192 comparator deals,1,280 MC32 resolutions,192 repeats,128
faults,resources and checkpoint immutability. Full PASS later requires the unchanged
greedy-direct4x1,250 quick5k gate. Snapshot/ledger SHAs
67bbfb66989bb1ec1978f7faa3299c9075062a2b42fa4617e1b97e014d83527c /
3bdd89dfd55a6c71ac2f27f8f3ebec91d8db6284f2bce00bef473edbf41ed257.
All implementation/output paths are absent;no probe,qualification,GPU,checkpoint,
network,Slumbot or official hand ran. Latest formal H11 remains -100.2475bb/100
CI95[-112.4067,-88.0883],last quick5k -146.1726;behavior windows0;L0;all four
non-V6 families remain;route exhaustion false;goal ACTIVE. Next later only is one
fresh RS007 implementation,ledger-derived deep test,exactly two probes,implementation
audit,one qualification,result audit and exact judgment;stop before quick5k.

Current authoritative update (2026-07-23 00:46 EDT): RS005 is terminal
`RS005_FAIL_CLOSED_PREQUALIFICATION_INVALID_DEEP_SELFTEST_FIXTURE_NO_RERUN`.
Implementation audit SHA
99bd9c01c41a67e142f5fa7ab561bf639b27a1c52f5f99ec38d5d800fd52bc71
PASS29/31;both probes passed zero-file/torch-absent,but the deep test used non-slot
`b600` after `b200`. Terminal judgment/audit SHAs
5efbab547651b060834d384642d6bf307314ca388e62ede9a23f53531f91aa6a /
5cf2af78e766d675dcfd4009c530fec9aeed6b9eae8597277cceef5585343c93.
The sole governance-permitted fresh correction RS006 changed only that fixture to
`b400`;its implementation audit SHA
e79c64f7707fbea2c498aa301074eaf4960e58a47d8b742c838f8c9c9257a039
PASS25/25 with deep test and two new probes. Its one qualification then failed before
rows at the immutable source transition `b200 -> b600`:the raise is poker-legal but is
absent from H11's nine-slot policy table. Failure/audit SHAs
7c781d2bbcc62dbb71b0e8c34a847f5e6a7331e13cb2ada178bdd70f143b127e /
ab32b727442707f5a7cd857b2867c346c95bb89b67a3c4847cca6feb2f1cdf99
PASS31/31 establish
`RS006_FAIL_CLOSED_PREOUTPUT_PUBLIC_LEGAL_ACTION_VERSUS_POLICY_SLOT_CONFLATION`.
Only invocation exists;result/audit absent;never repair,rerun,reclassify or quick5k
RS005/RS006. WS007 prereg/audit and result/audit SHAs
0861aefb5c94deafa6f78a6f1b85b8cbe48ff3ae0c6d313a65bd9464d9f7c268 /
e5e53f632816591bf0c27867385e4be38a35440afce96fa6601bf9b986e30c53
and
e4e601388623742f941084a48903501384de9dd085f447f0f60d4487493abb34 /
9046bf3bc4e56114e27588baa6dca5dfa7f1e7f3a974bef4313b2b205b616a1f
PASS25/25 select
`RS007_DUAL_DOMAIN_FULLY_LIVE_RESOLVER`:public transitions must accept every exact-cent
poker-legal observed/opponent action,while H11 hero choice remains restricted to its
exact executable slot table. A future design must cover full/short-all-in and reopen
semantics,replay29,878 rows/24,878 adjacent transitions,and preserve terminal/payout,
MC32,resource,quick5k and formal bars with no projection/drop/collision/renormalization.
Snapshot/ledger SHAs
5f404b2608d87657b8487b86baa9100256b34db6e8d3e4f205eb73b49135f0a7 /
4908507a2b0a63698694581a3bc2f4cc15e6867a22e80693bc0c5f28dcaa0cb4.
Latest formal external H11 remains -100.2475bb/100 CI95[-112.4067,-88.0883];
last quick5k -146.1726. Behavior windows0;new checkpoints0;network/Slumbot/official
hands0;L0;all four non-V6 families remain;route exhaustion false;goal ACTIVE. Stop
before RS007 registration. Next is separately registered RS007 design preregistration
plus independent preimplementation audit only;no implementation,GPU,evaluator,
Slumbot,checkpoint,quick5k or official hands.

Current authoritative update (2026-07-23 00:12 EDT): fresh RS005 identity/token are
5a01b095e04a242d79f0a20907a3e6f9d59c61780cf9a73765138cdb1f205bde /
5a01b095e04a242d79f0a20907a3e6f9. Preregistration/audit SHAs
70a232c8cbbef807e2530ba19e35f887b143d9e0f226cd443385d04e9a0a0c8c /
7f6b4800a7c22588f01fc02f8b1c632d8496fc2737fc8c0187faa39943d735c4
PASS170/170 bind26/26 exact inputs and establish
`RS005_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.
One fresh fully-live state exclusively owns public actions,exact-cent commitments,
legal executable slots,street/chance advance,board runout,terminal class,uncalled-
excess refund and zero-sum payout. HUNLGameState,HUNL action/chance/`is_terminal()`/
`payoff()` and RS004 runtime reuse are forbidden;only pure `compare_hands()` is
permitted. Fold and showdown payout equations are frozen in cents,with showdown
`M=min(total0,total1)` and unmatched excess returned. Qualification requires29,878
ledger rows,584 prefixes,24,878 transitions,6,921 live interfaces,8,192 synthetic
states,20x64 terminal-utility rows,1,280 resolutions,192 repeats,128 faults,MC32/
resource/fallback gates and checkpoint immutability. Full PASS later mandates one
greedy-direct4x1,250 quick5k. Snapshot/ledger-shard SHAs
ac4b514e7874ff3e7ef9ccba5cd26a7988ec1e37c23c51e904813d5d7343797b /
1eaf9b4c4605d7c367bea9e7889f7e0a85a1745d492e762d3576fd895ae2296a.
All implementation/output paths are absent. No implementation,probe,qualification,
training,checkpoint,network,evaluation or Slumbot hand occurred. Behavior0;control49;
official0;L0;route exhaustion false;goal ACTIVE. Next later only is one fresh combined
implementation,deep test,exactly two zero-file probes,implementation audit,one
qualification,result audit and exact judgment boundary;stop before quick5k.

Current authoritative update (2026-07-22 23:55 EDT): WS006 atomic result SHA
52dd1e0880ea7cac9197f2e8fef367f05d888816160d66e517b1dd563fe2ae42
(20,666B;embedded verification PASS15/15) applies the frozen nine gates and selects
rank1
`RS005_MATERIALLY_NEW_FULLY_LIVE_TERMINAL_UTILITY_RESOLVER` PASS9/9,then stops.
LG003,FA003 and CT003 were not evaluated after the first full PASS and remain open;
route exhaustion is false. RS005 is not an RS004 correction:one future fresh identity
must remove HUNLGameState from the rollout state and make an exact-cent live state the
exclusive owner of public action,commitment,legality,street/chance advance,board
runout,terminal class and exact payout. Only the separately frozen pure
`compare_hands(hole0,hole1,five-card board)` primitive is permitted;HUNL action,
public transition,chance,`is_terminal()` and `payoff()` are forbidden. The later
registration must freeze new code/output/seeds,exact fold/all-in/river-showdown and
zero-sum payout equations,29,878 ledger rows,584 prefixes,24,878 transitions,6,921
live interfaces,8,192 synthetic states,terminal-class coverage,MC32/resource/fallback
gates and mandatory complete quick5k evidence. Snapshot/ledger-shard SHAs
bdac818a018e55fe006debb16be16940b205840992891771bc52eafda4e16e99 /
6cac3754184f8e2f228c6350dcc01821e7dc7d6da48f3ea9e3b2294c0297ffc6.
No candidate registration,implementation,probe,qualification,training,checkpoint,
network,evaluation or Slumbot hand occurred. Behavior0;control48;official0;L0;goal
ACTIVE. Next later only is one unified RS005 candidate-specific preregistration plus
proportionate independent audit;stop before implementation or execution.

Current authoritative update (2026-07-22 23:35 EDT): WS006 post-RS004 simplified
route-review identity/token are
68f32e076fc5c7ecc7e680f2ba5b75280e2fd19fed3df9332ab6bc2a594085ac /
68f32e076fc5c7ecc7e680f2ba5b7528. Preregistration/audit SHAs
816984ce14e12d8eaf5dfbace545a4efeeba0179df2c3b6328950a8550505b97 /
9581a83bde3ff442c7238179fe1f40162426f67295fee7ecb0a8f4e338015539
PASS54/54 bind13/13 exact frozen inputs and establish
`WS006_REGISTERED_PREDECISION_AUDIT_PASS_RESULT_LATER_ONLY`. The frozen order is
RS005 materially new fully-live terminal-utility resolver,LG003 materially distinct
nonrecovery league,FA003 guaranteed-distinct-pair live-aligned teacher BC,then CT003
fundamentally new critic/target. One future atomic result must apply nine fixed gates
in order and select the first full PASS;missing evidence is NONPASS. RS005 is eligible
only if the exact-cent live ledger exclusively owns public transition,executable
action,legality,chance runout,terminal and payout while HUNL is limited to a pure
hidden-hand comparator;relabeling/repairing RS004 is insufficient. Snapshot/ledger
shard SHAs
a8888d005a4a7c147a55075dcf4e3d7597ad15b02f53e5e4bcdb9c650d238ede /
dc689188457d8dbc5697f18f57fd2301969110aecf4a43588ed406e105b083a5.
The registered result path is absent;selected candidate NONE. No implementation,
probe,data,asset,training,GPU,checkpoint,network,evaluation or Slumbot hand occurred.
Behavior0;control47;official0;L0;route exhaustion false;goal ACTIVE. Next later only
is one atomic reporting-only WS006 result with embedded verification at the exact
registered path;stop before candidate-specific registration or execution.

Current authoritative update (2026-07-22 23:18 EDT): RS004 is terminal
`RS004_FAIL_CLOSED_QUALIFICATION_LIVE_LEDGER_HUNL_TERMINAL_SEMANTICS_MISMATCH_NO_RESULT_NO_QUICK5K_NO_RERUN`.
Implementation audit SHA
259a370d77725d28e4f26b018242ba3879083383a6e74ed461c5e0b9cf6239c3
PASS31/31 binds runner/launcher/result-auditor/implementation-auditor SHAs
3041e15ae0398579681d61995dd100d84297228200f8815d749b8e12407d315a /
065c248b3631b6c1ffdf3fe11b0322a00109816fe8fbf0193883c081e17d93ea /
2b1962679b5946d4fb2e68d55309bb1a54ea7cef70f0b4eeeca015fd535d955a /
4e58e596b5eb87f007ebaed278fae04df556b54acfb29db25568639acf42c598,
the source-scoped5,000-hand census,a full deep self-test and exactly two zero-file
launcher probes. The sole qualification nonce RS004_QUALIFICATION_2036972296 exited1
after observed8.2s during paired-MC32 rollout when `apply_live_increment()` reached
`assert_mirror_public()` with live exact-cent ledger terminal true but HUNL
`is_terminal()` false (`RuntimeError:mirror_terminal_mismatch`). Before failure,
29,878/29,878 ledger rows,584/584 prefixes,6,921/6,921 live interfaces and
8,192/8,192 synthetic ledger+mirror+interface rows were written and independently
recounted exact. Resolution/repeat/fault/metrics/result are absent. The one
launcher-owned result-audit attempt exited1 because result.json is absent;result-audit
output is absent. This is a scientific interface-contract failure after valid root/
synthetic admission:at least one reachable future transition falsifies the registered
exact HUNL hidden-utility mirror. It proves no resolver benefit,fallback,latency,
resource,Slumbot improvement or strength,and does not exhaust the resolver family.
Preserve RS004 code and partial root read-only;never repair,rerun,extend,reconstruct,
mutate,apply a second correction,launch quick5k or adopt it as qualified. Judgment/
snapshot/ledger-shard SHAs
342e5643083e4b21552305815f7ad3cf0926f51d72e29aa03a7dbe40ec5dd7c9 /
990fc70b6c2ff49c6c577947f1cd014f483b7a1e741385a394190a980d9ffb41 /
f6968c3f43f3f2a9f5e8fd050c7f4ce68cbc9bd4563f536a838a35dad05edc97.
Checkpoint unchanged;training/network/Slumbot/official hands0;behavior0;control46;L0;
route exhaustion false;goal ACTIVE. Next later only is a separately registered
simplified reporting-only post-RS004 route review re-ranking LG003,FA003,CT003 and any
materially new fully-live terminal-utility resolver;stop before result or execution.

The 2026-07-22 23:04 update below is historical.

Current authoritative update (2026-07-22 23:04 EDT): fresh RS004 identity/token are
a4f6cdb3461aa6ef4ea29af61938082ccfe2497ad4177aa16317292aad1a6dfb /
a4f6cdb3461aa6ef4ea29af61938082c. Preregistration/audit SHAs
d6fd7ec547c7fcaee1f42f3a4e8074525ca86f1bc25ddf0aef197bc0dc374b2b /
b00417328f267021ab27e84f43c1210732c0d3a5b4c20fc13e22f8fccf18f258
PASS58/58 establish
`RS004_FRESH_PREOUTPUT_CENSUS_KEY_CORRECTION_REGISTERED_PREIMPLEMENTATION_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.
This consumes the sole post-RS003 fresh correction allowance;no second correction is
permitted. The only correction is the future implementation auditor's independent
census key from dump-local `hand_idx` to `(dump source absolute path,hand_idx)`.
Independent recomputation gives4 dumps,29,878 rows,5,000 hands,584 prefixes,24,878
transitions,12,564 hero rows and6,921 hero-postflop rows,with indices contiguous within
source+hand. The old single key reproduces RS003's1,250/28,628/noncontiguous failure.
All original22 inputs plus four correction-provenance inputs rehash exact26/26.
Twelve selected RS003 science-contract objects preserve canonical SHA
458ffa6c7c282fa9e9f9c041b7e902e7e4480d2028e3d85a88627d233faff8ba:
behavior,live-cent ledger,live V5.5 interface,HUNL hidden utility,paired-MC32 LCB95,
H11 checkpoint,seeds,qualification/resource/fallback gates and quick5k trigger are
unchanged. Snapshot/ledger-shard SHAs
a5ab2a75aafc9840ea7624fe4e2737d3cbad0c160775e8452fc3b59cb6695ccf /
53e7436fac5b8569ba86acbfd774bb8d70f490ac0550475ac37b74c7241675ec.
All fresh implementation/output paths are absent;implementation/probe/qualification/
training/checkpoint/network/Slumbot/official hands0;behavior0;control45;L0;route
exhaustion false;goal ACTIVE. Next later only is one combined fresh RS004
implementation,deep test,exactly two zero-file probes,implementation audit,one
qualification,result audit and exact judgment boundary;stop before quick5k.

The 2026-07-22 22:54 update below is historical.

Current authoritative update (2026-07-22 22:54 EDT): RS003 is terminal
`RS003_FAIL_CLOSED_IMPLEMENTATION_AUDIT_PREPROBE_DUMP_LOCAL_HAND_KEY_COLLISION_NO_QUALIFICATION_NO_RERUN`.
The frozen runner/launcher/result-auditor/implementation-auditor SHAs are
0021463e9905a923d14f1c93f95ecd68f7294d907b963e016fb60b0f3eb1b334 /
a38a714185d702f5f9278c6bb2e078cb4a7b08ea044246085b7f0cfc5f57e1e8 /
b6a90a78b2bdf2bc2abe06d42f12badedefe59b5e90a9ed24c47420c9d35b787 /
6ce4385817b9ec5369e9ac53d1abc904db18e6b54a138f714e37eae2d1a95717.
The sole implementation-audit result SHA
2c50418b1d6a16aad8bda783a16bfeae86a8f93756c189479c8eca8c09cd10dc
passed20/21 static checks and failed only `independent_dump_census_exact` before
deep self-test or probes. Its auditor keyed rows by dump-local `hand_idx` alone;each
of four dumps restarts at0,so it falsely observed1,250 hands/28,628 cross-part
transitions instead of the registered and independently audited5,000/24,878. The
correct independent key is `(dump source,hand_idx)`. This is a pre-output control-plane
auditor defect,not a scientific result. Deep self-test/probe/qualification/result audit/
quick5k/training/checkpoint/network/Slumbot/official hands are all0;qualification and
quick5k roots are absent;behavior0;control44;L0. Preserve RS003 and every bundle file
read-only:never repair,rerun,probe,qualify,mutate or adopt a descendant. The active-goal
pre-output recovery rule permits exactly one fresh corrected identity whose sole change
is the independent census hand key;all science,inputs,checkpoint,seeds,gates and
external trigger must remain exact with fresh paths. Judgment/snapshot/ledger-shard
SHAs ceb707589bbecaa19e4b2135a23ec19e8b6c6442b8ebb232ca8c07df3a778b42 /
9b7e80f81798d762d6412615ed218164cd27d7118fcd909c6873950c28783b83 /
ad598fa845a80c1fac6b19140e215f42a7c4555f0b82af208b6543e4f4aa3ba0.
The live-native resolver hypothesis remains untested/open;route exhaustion false;goal
ACTIVE. Next later only is one fresh RS004 correction preregistration plus proportionate
independent preregistration audit;stop before implementation,probes,qualification or
quick5k.

The 2026-07-22 22:34 update below is historical.

Current authoritative update (2026-07-22 22:34 EDT): RS003 identity/token are
f7709e4bfba3febe0a829c10781054b557ead7d419428dc06736316980679fdb /
f7709e4bfba3febe0a829c10781054b5. Preregistration/audit SHAs
19a75a06e77919bf6cc9bc8bd871b70107a3ec2ee38cb3ccb8fad456788c706b /
f411bd44f0aa96d5692c0469db7a61f464939d9a340d3b5b72062bda10a0744e
PASS97/97 bind22/22 inputs and establish
`RS003_REGISTERED_AND_AUDITED_PASS_COMBINED_IMPLEMENTATION_QUALIFICATION_NEXT_ONLY`.
The sole behavior change is H11 hero-postflop greedy root selection to fresh live-native
paired-MC32 LCB95. Canonical public state is Slumbot action string plus a fresh integer
exact-cent ledger;root and all rollout actors use live V5.5 tensors and exact live
slot/increment identities. Current approximate commitment helper,HUNL observation/action
ownership,RS002 runtime/adapter import and any projection are forbidden. Independent
full-dump census proves5000 hands,29878 rows,12564 hero rows,6921 hero-postflop infosets,
584 prefixes and24878/24878 exact adjacent extensions. Qualification must cover all of
them plus8192 synthetic states,1280 resolves,192 repeats and128 faults;any contract or
hidden-information mismatch hard-aborts before external hands. Later combined boundary
creates four fresh files,deep-tests,two zero-file probes,implementation audit,one
qualification,result audit and exact judgment,then stops before quick5k. A complete
PASS triggers greedy-direct4x1250 with bb/100>-126.1726,aggression<=0.80,attempt>=0.95,
fallback<=0.02,contract violations0 and complete evidence. Snapshot/ledger-shard SHAs
629cb38457e6383c463ec5405191a860f449c05fc259f49be6a48e8cf0da62c0 /
78ec9e0cc77ebe9dec0aa0be35396c9d6d2e9375d88dbbfd6409b271a8758e97.
Implementation/qualification/quick5k absent;network/Slumbot/training/checkpoint/official0;
behavior0;control43;L0;route exhaustion false;goal ACTIVE. Next later only is the one
combined implementation-through-qualification boundary;stop before quick5k.

The 2026-07-22 22:14 update below is historical.

Current authoritative update (2026-07-22 22:14 EDT): WS005 atomic result SHA
6f6f5612f8309997aa3eda0bbbdc76c22568e7ae66144d571c5e70c5e46575f5
selects
`RS003_FRESH_LIVE_NATIVE_PLAY_TIME_RESOLVER` as the first candidate passing all9
registered gates. This is not an RS002 repair. Future RS003 canonical public state is
the exact Slumbot action string plus a fresh exact-cent per-player/per-street ledger;
every root and rollout actor observation comes from the live V5.5 encoder and every
action remains the exact live slot/increment identity. The current live
`compute_commitments()` is explicitly approximate and cannot be the oracle. HUNL may
own only hidden cards,chance and terminal utility under exact public-ledger cross-check;
HUNL observation/action reconstruction,nearest-cent mapping,projection,collision,drop
and renormalization are forbidden. Qualification must cover all6921 witnessed roots
and every distinct prefix for exact live tensors,masks,baseline H11 actions and
slot/increment identities,plus32 distinct common determinizations,paired LCB95,
resources,bit-exact fallback,traces and rollback. Boundary limit is one unified
registration/audit then one combined implementation/exact-prefix qualification/audit;
the first qualified endpoint immediately runs complete greedy-direct4x1250 quick5k.
LG003,FA003 and CT003 remain open/not evaluated. Snapshot/ledger-shard SHAs
419924239d19a098b4c75ace1d4fcf6a52a9986bc33c0fc5f0016a2f8a22e950 /
7ec9e114fcef2a77be38e99b8c2251f3796d03734af0a2cc9b16b5883416fabf.
No implementation,probe,qualification,training,GPU,checkpoint,network,evaluation or
Slumbot hand ran. Behavior0;control42;official0;L0;route exhaustion false;goal ACTIVE.
Next later only is one unified RS003 candidate-specific preregistration plus
proportionate independent audit;stop before implementation or execution.

The 2026-07-22 22:05 update below is historical.

Current authoritative update (2026-07-22 22:05 EDT): WS005 post-RS002 live-boundary
simplified route-review identity/token are
150ef48caea4872d5478a1af75ee0d24ff92b56f64bd823253775283d1b6bc6f /
150ef48caea4872d5478a1af75ee0d24. Preregistration/audit SHAs
314fbee1d3aa81573941917936ada967e2dfee5f471e11e3bb32e76ea2b1bd9c /
96b894b0964ecd099e4df2d2a9c51846cf3754cf06ec76a969efa1746b9fe33c
PASS58/58 bind23/23 exact inputs and establish
`WS005_REGISTERED_AND_AUDITED_PASS_RESULT_LATER_ONLY`. Independent static inspection
rederives the live-call/HUNL-call amount mismatch without executing or importing frozen
code and preserves RS002 terminal:fully exact live rows0/6921,action tables5490/6921,
minimum fallback1.0>0.02;no repair,retry,projection or external launch. Frozen rank is
fresh live-native RS003,materially distinct nonrecovery LG003,guaranteed-diversity and
live-aligned FA003,then fundamentally new CT003. The future atomic result applies nine
gates in order;the named blocker and actual live observation/executable-action contract
are entry gates,missing evidence is NONPASS,and the first full PASS wins. Snapshot/
ledger-shard SHAs
e127f8eb54ca944a48a59368f614be0c47ee735a51eea513db0953415a0a4494 /
5455d6a00819c7cc1251dc29766d75f706249334ffd9e1901c199e79bd7d6755.
No result,implementation,probe,data,training,GPU,checkpoint,network,evaluation or
Slumbot hand ran. Behavior0;control41;official0;L0;route exhaustion false;goal ACTIVE.
Next later only is one reporting-only WS005 atomic result with embedded verification at
the exact registered path;stop before candidate-specific registration or execution.

The 2026-07-22 21:54 update below is historical.

Current authoritative update (2026-07-22 21:54 EDT): RS002 is terminal
`RS002_TERMINAL_FAIL_CLOSED_LIVE_OBSERVATION_AND_ACTION_IDENTITY_GATE_NO_QUICK5K`.
Before any external hand,the thin live adapter SHA
4a96685662d12837337a8bf89be464454204c59b4f55687271ff535ccfd8c009
compared all6921 H11 witnessed hero-postflop rows. The first auditor SHA
b8e82a4e98c42e3a8fb391f9cfbc2a7514f97699a975fb6230d33ffdb6fb58b1
had a pre-output NameError from JSON `true`;CENSURE SHA
d30fab0ae4b427c003504022b8c004af2c1a10fcbb1f25e42c8fa62e42fa08d3
freezes it with old result absent/no rerun. The sole fresh correction identity
24fa2be71ecb38c1d773e9298fa98f2c839327b8c8501182b10428415208b38c
and wrapper SHA
c2e8b7f29d2e7538ae4c7a548ce5aa27af9fd774cf0f5ae1ba5253d2d9c2fa13
changed only that literal binding. Corrected audit SHA
bc2a490d9062469a0e76ea804ff12cd652ba1f33495f907804f8214e04bfa85e
has integrity PASS11/13 and exact scientific NONPASS:0/6921 preserve full live/offline
observation+action identity;all6921 action-history tensors differ,action tables match
5490 and mismatch1431,and legal masks mismatch33. Minimum fail-closed fallback is1.0
versus maximum0.02. Read-only localization shows6904 tensors become equal only by
zeroing live passive-action amount features;17 retain other differences. Projection,
same-slot/nearest-cent mapping or observation rewriting is a new design and forbidden.
Terminal judgment/snapshot/ledger-shard SHAs
78eeb4d20f7638aa6bdeaabfc08be118d9654d969f12a83e5c8daffe86cc1e9f /
fec11e4eaf0b8eba5110aa60395ed9d18228d63f71467eeadc3e613f6413eae4 /
67e1b6d3abef78adf3572b9f12dd647ede27b8d2ae434f85ece2a3d5f003fd31.
Offline qualification PASS is preserved only in HUNL scope;its quick5k eligibility is
superseded. Never repair/retry/project or launch RS002. Network/Slumbot/training/
checkpoint/official0;behavior0;control40;L0;route exhaustion false;goal ACTIVE. Next is
one simplified reporting-only route review ranking fresh live-native RS003,LG003,FA003
and CT003. Stop before candidate-specific implementation or external launch.

The 2026-07-22 21:35 update below is historical.

Current authoritative update (2026-07-22 21:35 EDT): RS002 exact judgment is
`PASS / RS002_OFFLINE_QUALIFICATION_AND_AUDIT_PASS_QUICK5K_WINDOW_NEXT_ONLY`.
Implementation audit SHA
fc77a2d376448c2b537b07371b0c7e1f77b7390232dbd6ec7f21c31431daf5e9
PASS23/23 binds runner/launcher/result-auditor/implementation-auditor SHAs
44826e22405661b964a01827d051c825e04c28c194544f57ddb890dd34c4fdb6 /
67f37ad4702ba799c0dfad1d533496887e90a0797b20439d6f615e2e4dcfa993 /
258219bbc8c8481b1df679d401acf70b311f100186fda345ab1207e4cdb88405 /
b45ffc41d95ebbececfccdfda1f1432c7228667cba802fb9493f84fc355911f0,
a complete deep self-test and exactly two launcher probes;both exit0/files0/device
exact. The sole offline qualification result/audit SHAs
a7b6e92b478075f12a9616dd9790f3acff278e6e0a37a668abf945edfae3b3b0 /
4009d3629297c0ff1dd1e91f0d909db1fc52aa1d00ab29410f4c755df312a45f
PASS25/25 and PASS34/34 cover8192 synthetic states,6921 witnessed public
reconstructions,1280 full paired-MC32 resolutions,192/192 exact repeats and128/128
baseline fault fallbacks. Error fallback is0.003125;562/1276 nonfallback roots change,
rate0.44043887147335425. Latency p50/p95/p99/max is0.07320925/0.12804534/
0.19779587/1.52846380s;quick5k projection0.10167951h,wall120.7954s,RSS1303.56MiB,
GPU peak85.10MiB. H11 remains exact SHA
96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13.
Judgment/snapshot/ledger-shard SHAs
2cec96506fa1f5ca55b73b8fcba7cabee5c4e0051bb4057e7dea4f1ee78a5bf2 /
07cf9dc2ce7fac27d8a85986336d80d262dfd18558495a2b51b1cac8f528662c /
98e47b979833b43b72175b43c0769a824af950a0ccc219e2a39c5d2fad5f56aa.
This proves offline feasibility only:no Slumbot improvement,strength,20k/100k or route
exhaustion. Behavior0;control/nonbehavior39;training/checkpoint/Slumbot/official0;L0;
goal ACTIVE. Next boundary is the already preregistered complete greedy-direct4x1250
RS002 quick5k. Implement/audit only the thin live-state adapter in that same execution
boundary with no scientific-rule change,then execute and judge the complete evidence
bundle. Stop this session before quick5k;it remains directional and no strength claim.

The 2026-07-22 21:03 update below is historical.

Current authoritative update (2026-07-22 21:03 EDT): RS002 paired-MC32 LCB95 root-
resolver preregistration/audit SHAs
93316de07812e6801cd6c83ddb7082b21841b981115a11c42ec3215c6b4563c7 /
e346a5b56ed4b5dd7239e6726ed2f5082d9e7a8e711cf26f2bd14e85661ea4bd
PASS101/101 establish
`RS002_REGISTERED_AND_AUDITED_PASS_COMBINED_IMPLEMENTATION_QUALIFICATION_NEXT_ONLY`.
Identity/token are
81b61579f99755eb755d8c3c1905c22f8333284e208faa67540ee813aea1ef43 /
81b61579f99755eb755d8c3c1905c22f;all19 inputs rehash exact. The sole behavior change
holds H11 SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13
bit-exact and replaces only hero postflop greedy root selection with deterministic
paired-MC32 one-sided95% LCB. It draws32 distinct hidden pairs without replacement,
uses common determinizations for all exact legal9-slot actions,rolls frozen H11 greedy
to terminal,and changes slot only when paired LCB>0;otherwise baseline is bit-exact.
Opponent/future/outcome conditioning and action projection/collision/drop/
renormalization are forbidden. One offline qualification freezes8192 synthetic states,
6921 witnessed H11 hero-postflop rows,1280 full resolutions,192 repeats,128 faults,
latency p50/p95/p99/max<=2.5/8/15/20s,quick5k projection<=12h and strict resource/
fallback gates. Snapshot/ledger-shard SHAs
080b837593fceaa0cb8efa439523d41876e253c20e2b087aafeb52f7a9e440a6 /
87d768cb2e60d91d759f16ae1e37ca98721949677e0c8458d0a1c61bd8dfdb3d.
Quick5k is prospectively fixed at greedy-direct4x1250 after qualification PASS;
directional PASS requires bb/100>-126.17260000000002,both postflop aggression maxima
<=0.80,resolver-attempt>=0.95,fallback<=0.02 and complete evidence. Latest formal100k
and H11 quick5k remain -100.2475 and -146.1726 bb/100. Implementation files0;
qualification/quick5k absent;behavior0;control/nonbehavior38;training/checkpoint/
evaluation/Slumbot/official0;L0;routes unexhausted;goal ACTIVE. Next later only:one
combined RS002 implementation,tests,two probes,implementation audit,one qualification,
one result audit and exact judgment boundary;stop before quick5k. Failure is terminal
with no repair/rerun.

The 2026-07-22 20:50 update below is historical.

Current authoritative update (2026-07-22 20:50 EDT): WS004 atomic result SHA
40a5404afd7875d93d42c330d0a307bf9c52c4fcf800eae0989594b420f6e7e8
with17/17 embedded verification selects
`RS002_FRESH_PLAY_TIME_SUBGAME_RESOLVER_ROUTE` PASS7/7. It rehashes the registered
WS004 preregistration/audit SHAs
bfa164108497df6a54a3aeab3ab412fb421477c88b08f8631cdea3fad5d6cd49 /
ed6a55eae1530fd3423a8d863f0149992acc46cf9282343c76372be8bfa9dc9c
PASS62/62 and all12 frozen inputs. FA002 Q01 is a structural scientific-design
failure:the frozen runner independently shuffles each hidden determinization with no
cross-rollout uniqueness guarantee,then hard-requires>=28 unique pairs among32 and the
actual attempt failed there before row return. It is not a path/invocation/checker
defect;FA002 remains terminal with no corrected Q01,relaxation,replay or reconstruction.
RS002 is one same-H11-checkpoint inference-time intervention. A later unified contract
must freeze exact200bb full-HUNL coverage,one-to-one executable9-slot identity,zero
illegal mass,determinism,p50/p95/p99 latency/memory,bit-exact baseline fallback,
Slumbot integration,complete traces,fail-closed abort and resolver-OFF rollback. It may
use at most two nonbehavioral boundaries:one candidate registration/audit and one
unified implementation/qualification/audit;then the first qualified resolver-on
endpoint must immediately run complete greedy-direct4x1250 quick5k. LG003,FA003 and
CT003 were not evaluated and remain open;route exhaustion false. Snapshot/ledger-shard
SHAs de761a15ece3c23688037e25dacb06c383cd35107059939e562763013e3f1dfd /
e810f092d3e13a46d4920fccb2942b74f9c80d9df7fdf890c155c2aa808a48fa.
Latest formal100k remains -100.2475 bb/100,95%CI[-112.4067,-88.0883];last screened/
behavior-changing checkpoint H11 iteration35051 remains -146.1726 quick5k. Behavior0;
control/nonbehavior37;new data/training/GPU/checkpoint/evaluation/Slumbot/official0;
L0;goal ACTIVE. Next later only:one unified RS002 candidate-specific preregistration
plus proportionate independent audit. Stop before implementation,probe,qualification,
evaluation,Slumbot or official hands.

The 2026-07-22 20:43 update below is historical.

Current authoritative update (2026-07-22 20:43 EDT): reporting-only WS004 post-FA002-
Q01 simplified route review preregistration/audit SHAs
bfa164108497df6a54a3aeab3ab412fb421477c88b08f8631cdea3fad5d6cd49 /
ed6a55eae1530fd3423a8d863f0149992acc46cf9282343c76372be8bfa9dc9c
PASS62/62 establish
`WS004_REGISTERED_AND_AUDITED_PASS_RESULT_LATER_ONLY`. Identity/token are
99a9bc69ece4a50b642c086917930a38715e00995abd883c40ba921b6a8bdf7c /
99a9bc69ece4a50b642c086917930a38;all12 frozen inputs rehash exact. Direct audit used
no executable checker and did not import,execute or replay the terminal Q01 runner.
Future result must classify the diversity failure from static evidence as structural,
control-plane or inconclusive;uncertainty is inconclusive and no classification reopens
FA002 or permits a corrected Q01. Frozen candidate order is RS002 resolver,LG003
materially distinct nonrecovery league,FA003 fresh guaranteed-diversity teacher design,
then CT003 fundamentally new critic/target hypothesis;first seven-gate PASS wins.
Selected work must reach a deployable checkpoint or valid external endpoint within at
most two further nonbehavioral boundaries. Snapshot/ledger-shard SHAs
dcfbca523120b1a1fd5ed88aa9aac84a4353bbb2ebd040ea457bca51305f4b5d /
fbe3437bfce72124310986b5bdf8e989cc8ba78505eca3e79bbf61baabcd95f2.
Latest formal100k remains -100.2475 bb/100,95%CI[-112.4067,-88.0883];last screened
and last behavior-changing checkpoint is H11 iteration35051,whose quick5k was
-146.1726,95%CI[-238.59789051053525,-53.7473094894648]. No behavior changed in this
campaign. Behavior windows0;control/nonbehavior36;data/assets/training/GPU/checkpoint/
evaluation/Slumbot/official hands0;L0;all four routes remain unexhausted;goal ACTIVE.
Next later only:one atomic WS004 reporting-only result with embedded verification at
the exact registered path. Stop before candidate-specific registration,implementation,
probe,data/assets,training,GPU,checkpoint,evaluation,Slumbot or official hands. The
next external trigger is the mandatory complete greedy-direct quick5k after a selected
route creates an eligible behavior checkpoint.

The 2026-07-22 20:34 update below is historical.

Current authoritative update (2026-07-22 20:34 EDT): FA002 Q01 is terminal
`FA002_Q01_FAIL_CLOSED_PREOUTPUT_HIDDEN_PAIR_DIVERSITY_EXCEPTION_NO_RESULT_NO_RERUN`.
Exactly one frozen Qualification attempt used execution nonce
FA002_Q01_EXECUTION_2034972233 and contract SHA
e2fbee43c4ec2a8d9e17b37877a9e6a43344189038cd8687569168654cfb6662,
then exited1 after82.2s when an MC32 worker raised
`RuntimeError:hidden_pair_diversity_below28`. Invocation/reached-state SHAs
7ce4357a5e7050afaec2a88549acb1d8f2fc7387461764526b8c8cbc19ffbd53 /
33f7d6773d42f79b4371efa7ec606deadc5d0fd71b90613aa5aadd09f9d1046b;
the gzip independently recounts120,000 rows. Quality/repeat/metrics/result outputs are
absent and preserved quality/repeat rows are0. Exactly one launcher-owned Audit then
exited1 because result.json was absent;result_audit.json is absent. Judgment/snapshot/
ledger-shard SHAs
e6d230c83127fafc19b5003fafe0b5e9e5363420415c1329c9ab6ae108b6ed31 /
4efd9c253bbb0ee3adaa74eed76c3f5ac5a94c376f6d9a4cdc7c0cc26b8f6303 /
870e642f35b228bac239869d4c582c7cfc573ab565918e7e81fa9b0467ac2c0c.
This proves only that at least one MC32 task violated the registered hidden-pair
diversity minimum28/32;Q01 is neither PASS nor a complete registered NONPASS and no
teacher-quality/resource/BC/behavior/strength inference is allowed. Preserve all code,
partial output and both attempts read-only;never repair,rerun,reconstruct or reclassify.
Behavior windows0;control/nonbehavior35;asset/training/GPU/checkpoint/evaluation/
Slumbot/official hands0;L0;route exhaustion false/unjudged;goal ACTIVE/incomplete.
Next later only:one separately registered reporting-only simplified post-FA002-Q01
route review plus proportionate independent audit to classify the diversity failure,
re-rank all four non-V6 families and select one fresh highest-information-gain route.
No automatic corrected Q01. Stop before implementation,probe,qualification,asset
generation,training,GPU,checkpoint,evaluation,Slumbot or official hands.

The 2026-07-22 20:24 update below is historical.

The 2026-07-22 20:05 update below is historical.

Current authoritative update (2026-07-22 20:05 EDT): FA002 unified candidate
preregistration/audit SHAs
18765838ce043a6f560162770aeeb665eebac6a42b53f580934f6c69d6d849a7 /
004090c0ab90388c9e494cf503f572a463fda38eaf65e6a41af886846db6e5f7
PASS161/161 establish
`FA002_UNIFIED_CANDIDATE_SPECIFIC_PREREGISTRATION_AUDIT_PASS_Q01_IMPLEMENTATION_READY_ONLY`.
All17 frozen inputs exist with exact bytes/SHA256. Identity/token are
61e5047f8820e9df19733e57c257a04a35442f07a3299fca04b8c1183a668d88 /
61e5047f8820e9df19733e57c257a04a. The one future behavior intervention is
policy-first soft-target BC from exact H11:train card/action/extra encoders,trunk and
policy head;freeze value-head parameters;no PPO,self-play,architecture,observation,
action,reward,league or resolver change. Teacher is information-set-correct exact-V5.5
MC32 4x8 over24 witnessed depth/street/actor contexts;unsupported CFR,bucketed,
legacy54,Path-1,PCV019,TNQ and Q006 rows are0. One combined CPU-only Q01 must establish
120k reached states,6,144 balanced quality rows,768 repeats and a fresh <=168h/<=100GB
all-20M projection. Only later Q01 PASS can admit eight2.5M asset windows totaling
14M/3M/3M depth rows and18M/1M/1M train/validation/test,then one three-epoch H11 BC
window and exactly one eligible checkpoint. Its mandatory greedy-direct Slumbot quick5k
requires4x1,250 complete hands,bb/100>-126.17260000000002 and played/greedy postflop
raise+all-in each<=0.80 for directional PASS;only bb/100>0 may enter a separately
registered20k gate;quick5k proves no strength. Snapshot/ledger-shard SHAs
c010ff2794b12f5c54325d51b3f96709400977169adb78828620a4092d89ba09 /
92056c3ab4cd7bda63e321b22dbe26c223add3faed7fa85e8d51fa7ae49f5fde.
No implementation,probe,qualification,row,training,GPU,checkpoint,evaluation,Slumbot or
official hand ran. Behavior windows0;control/nonbehavior33;official0;route exhaustion
false/unjudged;L0;goal ACTIVE/incomplete. Next later only:implement the fresh FA002 Q01
runner/launcher/auditor and independently audit implementation with exactly two fresh
launcher-bound zero-file CPU contract probes;stop before qualification,data/assets,
training,GPU,checkpoint,evaluation or Slumbot.

The 2026-07-22 19:48 update below is historical.

Current authoritative update (2026-07-22 19:48 EDT): WS003 atomic result SHA
eb1dd37b19a3e55f4206b0523369da5ef1f65ad0b48394866354661bc6b5c443
uses preregistration/audit SHAs
093d5ee322431f6e1158790e3d13a5ba3e59fe9f1e5b461a157205c283461821 /
c3d096126187766d465d7182171a19ebc687915e24536a3851026d4fd8247924
PASS52/52 and rehashes9/9 frozen inputs exact. Embedded verification replays the
registered four-candidate order and six gates. Rank1
`FA002_EXACT_V55_CFR_BC_TEACHER_WARM_START` passes6/6 and is selected for one later
unified candidate-specific preregistration plus proportionate independent audit only.
RS002,LG003 and CT003 were not evaluated after the first PASS and remain scientifically
open/unexhausted. Late competing e469 registration/audit have authority NONE under
CENSURE SHA
6b2e5d43ce6fe5c5cb46c4e02c9f1a4f6eab050af61f8abb0ad9d3f072ff7186
PASS24/24 and do not affect WS003. This proves selection only:not teacher quality,BC
benefit,full-scale resource feasibility,checkpoint eligibility,Slumbot improvement,
strength or route exhaustion. Snapshot/ledger-shard SHAs
6660b8edd870667445a60f0d24b189a4ef360f7d69cbc58e7ed105090de54726 /
5a59ec01f2b36678b2ddc1acb18a0b6a54bc02a76df0392f692a5ec3e9249f05.
No candidate registration,implementation,probe,data,asset,training,GPU,checkpoint,
evaluator,Slumbot or official hand occurred. Latest formal V5 official100k remains
-100.2475bb/100,CI95[-112.4067,-88.0883];H11 quick5k -146.1726 is directional only.
Behavior windows0;control/nonbehavior32;official hands0;route exhaustion false/unjudged;
L0;goal ACTIVE/incomplete. Next later only is one unified FA002 candidate-specific
preregistration plus proportionate independent audit;stop before implementation,probe,
data/asset generation,training,GPU,checkpoint,evaluation or Slumbot.

The 2026-07-22 19:41 update below is historical pre-result registration authority.

Current authoritative update (2026-07-22 19:41 EDT): WS003 post-CT002 simplified
route review is content-addressed,registered and independently audited. Identity
5365a5621df98b4fbf4a2c81db13269d9779aba972a5ca56ac35429f9aff969c
(token5365a5621df98b4fbf4a2c81db13269d);preregistration/audit SHAs
093d5ee322431f6e1158790e3d13a5ba3e59fe9f1e5b461a157205c283461821 /
c3d096126187766d465d7182171a19ebc687915e24536a3851026d4fd8247924
PASS52/52 rederive identity,rehash9/9 frozen inputs and preserve the terminal 7fa
chain without adopting its descendants. Frozen candidate order is FA002 exact-V5.5
CFR/BC teacher warm-start,RS002 play-time resolver,LG003 materially distinct
nonrecovery league,then CT003 only as a fundamentally new critic/target hypothesis
and never a second corrected CT002. A later atomic result must apply six gates in
order,select the first PASS and stop;route exhaustion requires frozen no-viable-route
evidence for all four families. Future result is absent. Snapshot/ledger-shard SHAs
ab2370f6404cdde1178a93f85db0f9e196125117020a8ade033c8d31c6975eef /
caeb685a8b91d69e91996d98730c4d02d787486d58d9dcb4b8e33bb34b898267.
No candidate-specific registration,implementation,probe,data,training,GPU,checkpoint,
evaluator,Slumbot or official hand occurred. Behavior windows0;control/nonbehavior31;
official hands0;route exhaustion false/unjudged;L0;goal ACTIVE/incomplete. Next later
only is one deterministic atomic WS003 result with embedded verification at the exact
registered path;stop before candidate-specific registration or execution.

The 2026-07-22 19:31 update below is historical terminal-chain evidence incorporated
by WS003.

Current authoritative update (2026-07-22 19:31 EDT): corrected CT002 identity7fa
remains terminal. Late-descendant CENSURE SHA
e7b40e933ee6e669b5302554201bf5c3d9b72a2ef84f9c1228ae65a2d2c83ac1
PASS28/28 records that after terminal parent
1f4647ab1d9e901d46158e43f38d31f0845bc0bc4bc3626cb32d532caeecd903
and prior reconciliation
919d4c3a725c502a45aa8754ef25d04806f013a24070434238053f86cc0c869b,
the auditor was mutated to
d6af2edddcd3c54991636fc55850e44bbeb393737873db48c4cfb929ceb409ea
and audit-result SHA
4981876ec5f0ee858608dd0e50f09b5cfb14e8978a185bfe20c3999597a84420
appeared. Stable runner/test/launcher SHAs remain1a2ade...1fd5 / 4eeb6e...2f5 /
bb9cf0...cd9. All final descendants and every late-result claim have authority NONE;
preserve read-only and do not inspect,test,execute,adopt or create descendants. The
terminal no-rerun judgment remains binding. Prior reconciliation is superseded only
for auditor-final-hash and audit-result-absence census. Output root remains absent;
authoritative post-terminal probe count is UNOBSERVABLE_NO_AUTHORITY. Data,calibration,
PPO,GPU,checkpoint,evaluator,Slumbot and official hands remain zero;CT002 science is
untested. Snapshot/ledger-shard SHAs
f2ae173afc1108589a78b159091d5bb6e9df46ce29b00e265e46d4e804653e1f /
fd288c57ec4d1177c54048d0e7ef2a048a36e8737ee4de824997415965a365d9.
No second corrected identity. Next later only is one simplified reporting-only
workflow/route-review preregistration plus proportionate independent audit;stop before
review result or execution. Latest formal V5 official100k remains -100.2475bb/100,
CI95[-112.4067,-88.0883];H11 quick5k -146.1726 is directional only. Behavior
windows0;control/nonbehavior30;FA002,RS002,LG003 open;route exhaustion false/unjudged;
L0;goal ACTIVE/incomplete.

The 2026-07-22 19:27 update below is historical and is superseded only for its auditor
hash and audit-result-absence census.

Current authoritative update (2026-07-22 19:27 EDT): corrected CT002 identity7fa
remains terminal under parent CENSURE SHA
1f4647ab1d9e901d46158e43f38d31f0845bc0bc4bc3626cb32d532caeecd903
PASS30/30. Post-CENSURE reconciliation SHA
919d4c3a725c502a45aa8754ef25d04806f013a24070434238053f86cc0c869b
PASS26/26 records that the same registered runner/test/launcher paths were mutated
after the terminal parent. Stable final SHAs are
1a2ade05051eb4fd1ac3a5bec0e5e151dc1ccdf19a8fe8bdd6977ce6d5f81fd5 /
4eeb6e4b9904130b1a4a1886c7636d3ba9afe0b013396776a27762f592c5b2f5 /
bb9cf001dc6bec0bbb17a245fc2b11c83d80b717fa24f3ed17fd259066636cd9;
the auditor remains
26e0305af78ed832b254b942be0cb85b0e6119470ea94db0031fcd262a01562c.
All four final descendants have authority NONE:do not inspect,test,execute,adopt or
create descendants. The parent's earlier same-path bundle census is superseded only;
its terminal no-rerun judgment remains binding. Audit result and output root remain
absent. No authoritative post-terminal probe artifact exists,so probe count is
UNOBSERVABLE_NO_AUTHORITY rather than inferred zero. Data,calibration,PPO,GPU,
checkpoint,evaluator,Slumbot and official hands remain zero;the scientific hypothesis
is untested. Snapshot/ledger-shard SHAs
28c04179d4f2dd3497e2739c1c1f2c582a79348d84b9eaf35b58e98e697a389c /
b415fadde450fab2ff08a29c227f3674a98c3d0a20b269893020cebabad97dec.
No second corrected identity is allowed. Next later only is one simplified reporting-
only workflow/route-review preregistration plus proportionate independent audit;stop
before review result or execution. Latest formal V5 official100k remains
-100.2475bb/100,CI95[-112.4067,-88.0883];H11 quick5k -146.1726 is directional only.
Behavior windows0;control/nonbehavior29;FA002,RS002,LG003 open;route exhaustion
false/unjudged;L0;goal ACTIVE/incomplete.

The 2026-07-22 19:19 update below is the terminal-parent state whose bundle census is
superseded only by the reconciliation above.

Current authoritative update (2026-07-22 19:19 EDT): corrected CT002 identity7fa is
terminal
`CT002_7FA_IMPLEMENTATION_AUDIT_FAIL_CLOSED_PREPROBE_TEST_OUTPUT_COUNTER_NO_RESULT_NO_RERUN`.
CENSURE SHA
1f4647ab1d9e901d46158e43f38d31f0845bc0bc4bc3626cb32d532caeecd903
PASS30/30 binds runner/test/launcher/auditor SHAs
8eb744c0e0531620404ea7a5cc032ee791ca090a4afd62645e2a8ff7e021ce7e /
aa05dad0cf14c5b8b15d49ec66bebb3d61b052cd88ef6aeddda58ebea616d6f3 /
f06fd1c9f5fd79c835d38b707e88dc854c44a1d693fba8d855ab2c95dce42e34 /
26e0305af78ed832b254b942be0cb85b0e6119470ea94db0031fcd262a01562c.
AST3/3 and the final direct unit-test run PASS13/13,but the sole implementation-audit
attempt exited1 before checkpoint inspection or probes because a literal ` ... ok`
counter observed12:the expected argparse rejection split one test label from its final
`ok`. Exactly0 ContractProbe children launched;implementation-audit result and output
root are absent,and data,calibration,PPO,GPU,checkpoint,evaluator,Slumbot and official
hands are zero. This is pre-output checker failure only;the scientific hypothesis is
untested. Preserve all four files read-only;never repair,rerun,probe,execute or create
descendants. The ae78 collision plus this 7fa checker defect are the second recurrence;
7fa consumed the sole fresh-correction allowance,so no second corrected CT002 identity
is allowed. Snapshot/ledger-shard SHAs
bc0beac990ed6572ef94fa0ef744a9989ca19dca30991f20766b3de9b68b16dc /
b0e2c7051d383674ee5e6ae2b4378de2b1d701fa55b500b35eca98ce981c77ba.
Next later only is one simplified reporting-only workflow/route-review preregistration
plus proportionate independent audit to select FA002,RS002,LG003 or a fundamentally
simplified critic route if supported;stop before review result or execution. Latest
formal V5 official100k remains -100.2475bb/100,CI95[-112.4067,-88.0883];H11 quick5k
-146.1726 is directional only. Behavior windows0;control/nonbehavior28;FA002,RS002,
LG003 open;route exhaustion false/unjudged;L0;goal ACTIVE/incomplete.

The 2026-07-22 19:03 update below is historical preimplementation authority superseded
by the terminal CENSURE above.

Current authoritative update (2026-07-22 19:03 EDT): the sole corrected CT002
implementation identity is
7fa29a5e2f003b9fe4236c23fdad20933388345b669b982437c570437cb480f1
(token7fa29a5e2f003b9fe4236c23fdad2093). Preregistration/audit SHAs
4c21f92dc37b668a57e850a07ab279ebe90f3115b22b7aff48f66b8f674ac1b2 /
7dc738ce349008fee8f08b79ffc3c094b314ed1f2280f70a62a6f93755b4233a
PASS70/70 rederive the content-addressed identity,rehash10/10 direct authority inputs
and28/28 transitive scientific inputs/tools,and preserve the exact ae78 scientific
design. Only identity,absolute paths,fresh random-realization seeds and two future
ContractProbe nonces change;the critic-only calibration distribution intervention,
H11 source/five-member pool,250k/50k rows,1000 value-head updates,mechanism gates,
matched5M PPO arms,quick5k gates,Stage-B and promotion chain are unchanged. Workflow
is simplified to one registration and one direct static audit with no executable
checker. A later competing corrected registration ac12a5a513d970a6906ec415d7743be9
has authority NONE under CENSURE SHA
4536653f3340fa930fd981171ea4f4f0b58e9ee1ce2455c4aa572ca6fe9e03b3
PASS16/16;never audit,implement,probe or extend ac12. Its sampled 7fa-pending label is
superseded by the immutable PASS70 audit;its ac12 judgment remains binding. All 7fa
future code/audit-result/output paths are absent;no implementation,probe,data,
calibration,PPO,GPU,checkpoint,evaluator,Slumbot or official hand occurred,and the
hypothesis remains untested. Snapshot/ledger-shard SHAs
587594cb3858e8e64101261f2de10b5b6d8d54d261928b6187edfa7093806e29 /
6f9d3bcdf8487c8170bfc01971f3c4e7c3a277c680f0658c5b96e8999efe7a99.
Next later only is exactly one clean-room implementation on registered 7fa paths plus
one independent implementation audit with exactly two new-nonce launcher-bound
CPU-only zero-output probes;stop before data generation. Latest formal V5 official100k
remains -100.2475bb/100,CI95[-112.4067,-88.0883];H11 quick5k -146.1726 is
directional only. Behavior windows0;control/nonbehavior27;FA002,RS002,LG003 open;
route exhaustion false/unjudged;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:52 update below is historical pre-corrected-registration evidence.

Current authoritative update (2026-07-22 18:52 EDT): ae78 remains terminal and its
post-CENSURE descendants have authority NONE. Reconciliation SHA
f859f269bcba2f79ea1be436790779768bfe7783db1b58b556b558b3fe0f07ee
PASS32/32 binds the stable post-terminal runner/launcher/test/auditor SHAs
e8cbe5427778178737976665aa526c855371ad8704667e1af7f8dc8de4bc8356 /
e285cb0ebcce29f43dc182e9668afee084c470735ca5883f6b8e080bea711909 /
c1bc4df74775c237b75dec69b4e49efe8921aada042cc59b1651d9746d9679b3 /
871835f769f137844d26ed3a6614d99a452dea29021c107725f6dd77edbd0d78
and the late implementation-audit result SHA
349a5c6fefe4767449bf632b9840b1dab079d6ce005dd1510d39e4996292e113,
which reports PASS49/49 and exactly two launcher-bound zero-file ContractProbe
children. These artifacts appeared after parent CENSURE
8f2b4c114a1ba04f1cd57f565babf91d5cc995476ffa4531b9e48f78e1746399
had terminalized ae78;therefore the final bundle,audit PASS and both probes are
provenance-only with authority NONE and cannot establish readiness or consume the
fresh corrected identity's future new-nonce/new-path probes. The parent bundle hash
census was TOCTOU-stale and is superseded only as artifact census;its terminal
classification remains binding. Registered output root remains absent;no data,
calibration,PPO,GPU,checkpoint,evaluator,Slumbot or official hand occurred,and the
critic-calibration-distribution hypothesis remains untested. Snapshot/ledger-shard
SHAs 9e3edf7d08c0786028e7e31e26c089b9f6281c87ecc67a651ece625a45b00d90 /
e7bae921e49c9eb5fd2f800360424f4f520434c22843060b3b619a1e03182547.
Preserve every ae78 descendant read-only;never repair,rerun,merge,copy or extend it.
Next later only is exactly one fresh corrected CT002 identity preregistration plus
independent preimplementation audit on new absolute paths and nonces;stop before
implementation or probes. Behavior windows0;control/nonbehavior26;FA002,RS002,LG003
open;route exhaustion false/unjudged;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:44 update below is the binding terminal parent;its implementation
bundle census is superseded by the post-CENSURE reconciliation above.

Current authoritative update (2026-07-22 18:44 EDT): canonical ae78 CT002
implementation is terminal
`CT002_AE78_IMPLEMENTATION_BUNDLE_COLLISION_FAIL_CLOSED_PREPROBE_NO_RESULT_NO_REPAIR`.
CENSURE SHA
8f2b4c114a1ba04f1cd57f565babf91d5cc995476ffa4531b9e48f78e1746399
PASS32/32 binds the incompatible current runner/launcher/test/auditor SHAs
62acf3e7c31510d45a7aeb18cb134cfcf1e8e06fb599ac02c1a0a7f498e263f9 /
c648cb37cddbbc063a8a0390d109f9c65a3a75e7fe1db776cb5fa25b64325706 /
adb970ae5b2b20cafa840088d1a5fc40c0c7040033f4fb493ebaff9bc52715a9 /
fe2b05032f9da932edb0224617cb5560b50af86894c102df58d9ea1bb4bd24e9.
Concurrent same-path writes left two API families mixed:AST3/3 passed,but unit tests
were total10/pass1/failure1/errors8. Failure was preprobe;exactly0/2 ContractProbe
children ran,the implementation-audit result and output root are absent,and no data,
calibration,PPO,GPU,checkpoint,evaluation,Slumbot or official hand occurred. Preserve
all four ae78 implementation files read-only;never overwrite,repair,merge,select a
preimage,run probes or create descendants. The ae78 preregistration/audit remain
immutable scientific-design evidence,but implementation authority is NONE and the
critic-calibration-distribution hypothesis remains untested. Snapshot/ledger-shard
SHAs 1405692d94d8efc5dde94760bd0be9ae50c13445ca88264bf271e7a6e1705a7c /
4bc532994c7e43504e327817f4bcc4c6df6256fe09f6f5312c8ae277eb80e6ea.
Because this is a pre-output control-plane identity failure with unchanged science,
exactly one fresh corrected CT002 identity is eligible without route review. Next
later only is its preregistration plus independent preimplementation audit on new
absolute paths;stop before implementation,probe or execution. Behavior windows0;
control/nonbehavior25;FA002,RS002,LG003 open;route exhaustion false/unjudged;L0;goal
ACTIVE/incomplete.

The 2026-07-22 18:25 update below is historical preimplementation authority;its ae78
implementation authority is superseded by the CENSURE above.

Current authoritative update (2026-07-22 18:25 EDT): the sole canonical CT002
candidate-specific preregistration/audit SHAs are
faef13eff5a57270bc59b43ff3272a3eb6bedf0fe43f0539494a2cd0993072da /
2426ca7663d9f347d7884a0e6ebf36831924f110acc316a5326f80fcfa04860e
PASS52/52 under identity/token
ae78e683c41a2abcff33eeae9fdad8adecd7db86db4827fe659583a2b33c4096 /
ae78e683c41a2abcff33eeae9fdad8ad. They bind20/20 frozen inputs,8/8 evaluation
tools,the exact H11 iteration35051/hands576021901 model/optimizer and all five pool
tensor identities,and clean-room V5.5/9-slot/value-head-only implementation sources.
The coherent intervention changes only critic calibration data distribution:self-play
returns control versus a fixed uniform five-member H11 opponent-mixture treatment;
actor/trunk/buffers,target,row/update counts,optimizer transform,later PPO and
evaluation are matched,and mechanism gates precede PPO. A later competing c216
preregistration/audit pair registered the same candidate under different identity,
bytes,thresholds and paths. Pair-reconciliation SHA
271205d8bfac55e6e985c238c0ec3f1ea803f805f33534242ac11c806b615158
gives the c216 pair,its snapshot/shard and every descendant authority NONE;preserve
read-only. Its earlier main-ledger canonical claim is superseded. Snapshot/ledger-shard
SHAs a5b41aadcbb7ef0fb3e0417b0cc56ca32724645b8cbdee39b80c035000b5b673 /
3e2e26cb6dfaa6d81de61fbb775b7ecd41131105c0b5da17fbc5049185b1dca1.
No implementation,test,dataset,calibration,PPO,GPU,checkpoint,evaluation,Slumbot or
official hand ran;method benefit remains untested. Next later only is implementation
of canonical ae78 plus one independent implementation audit with exactly two zero-
output probes;stop before data generation or behavior execution. Behavior windows0;
control/nonbehavior24;FA002,RS002 and LG003 remain open;route exhaustion false/
unjudged;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:24 update below is historical competing-pair evidence with authority
NONE;its c216 canonical claim is superseded by the reconciliation above.

Current authoritative update (2026-07-22 18:25 EDT): the sole canonical CT002
preregistration/audit SHAs
faef13eff5a57270bc59b43ff3272a3eb6bedf0fe43f0539494a2cd0993072da /
2426ca7663d9f347d7884a0e6ebf36831924f110acc316a5326f80fcfa04860e
PASS52/52 use token `ae78e683c41a2abcff33eeae9fdad8ad` and bind20/20 frozen
inputs,8/8 evaluation tools,the exact H11 model/optimizer/five pool identities and
four clean-room implementation sources. The only future causal intervention is
critic-only calibration data distribution:self-play returns control versus the fixed
uniform H11 opponent-mixture return treatment,with actor/trunk/buffers,target,rows,
exactly1000 value-head updates,optimizer transform,matched5M PPO and evaluation common.
Mechanism gates occur before PPO. A later competing c216 preregistration/audit pair
registered the same intervention with different identity,bytes,thresholds and paths.
Pair reconciliation SHA
271205d8bfac55e6e985c238c0ec3f1ea803f805f33534242ac11c806b615158
assigns the c216 pair,its snapshot/shard and canonical claim authority NONE;preserve
them read-only with no descendants. Canonical snapshot/shard/main-ledger SHAs
a5b41aadcbb7ef0fb3e0417b0cc56ca32724645b8cbdee39b80c035000b5b673 /
3e2e26cb6dfaa6d81de61fbb775b7ecd41131105c0b5da17fbc5049185b1dca1 /
a49e15fdfad6a027b3dddb04c1538fd459b8a2a5902b29438efbea17747b54e7.
No implementation,test,data,calibration,PPO,GPU,checkpoint,evaluation,Slumbot or
official hand ran;method benefit remains untested. Next later only:implement canonical
ae78 clean-room CT002,then one independent implementation audit with exactly two
zero-output probes;stop before data generation or behavior execution. Behavior
windows0;control/nonbehavior24;FA002,RS002,LG003 open;route exhaustion false/unjudged;
official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:24 c216 update below is historical authority-NONE provenance.

Current authoritative update (2026-07-22 18:24 EDT): CT002 candidate-specific
preregistration/audit SHAs
c7728ed025f990badb97b673ff944ee6943ab0e443170ae641471519a2478818 /
981426a5fad9ffe3725a81d5299960afdf3b6d4a32c6dd77c16584d790ee65e5
PASS54/54 freeze one causal variable:
`CRITIC_ONLY_CALIBRATION_DATA_DISTRIBUTION`,matched self-play-return control versus
the exact H11 active-pool opponent-mixture-return treatment. Both arms start exact H11
checkpoint SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13
at iteration35051/hands576021901. Actor,trunk,BatchNorm,pool,target,exactly2048
value-head-only updates,optimizer handling,matched5M PPO and complete paired-deal
greedy-direct quick5k screens are frozen common except consequences of the data
distribution. All14 frozen path/hash/byte triples and five active-pool snapshot
manifests rehash exact. The historical H11 clean trainer hash is absent;current
`train_v5.py` SHA9d42ff31a57c13ae8afd361b553fe9ea6e086c3e6d0c46328012f39b245b5310
is a CENSUREd LG002 descendant and is forbidden for import,copy,execution or fallback.
All future dedicated code/output paths remain absent. Snapshot/ledger-shard/main-ledger
SHAs 3110fbb9a3111d74df51c5e38333f5f6dc624ebb85be6850c211e01f494b3455 /
97f01b6a2009a972c847a9430ba0a81295f730228d794f5842ef859f857e1969 /
ab55406d5de16d2397c3eb7302a93862fd42981c5018e549c433854fd828d40b.
No implementation,test,dataset,asset,training,GPU,checkpoint,evaluation,Slumbot or
official hand exists or ran. Next later only is one fresh dedicated CT002 implementation
plus independent implementation audit;stop before dataset generation or any behavior
execution. Behavior windows0;control/nonbehavior23;all four route families open;route
exhaustion false/unjudged;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:07 update below is historical selection evidence.

Current authoritative update (2026-07-22 18:07 EDT): SIMPLIFIED_ROUTE_REVIEW001
canonical atomic result/audit SHAs
0ac4a83714df460dc3533d519eecc5a89e83cafcedffbd6c8b02c5e0e0faa851 /
5c01fff4e4f756610dea66d202dd5c994eb6af55c8dea002b0e8975e061abb77
PASS27/27 select rank1
`CT002_FRESH_CRITIC_OR_TARGET_CAUSAL_INTERVENTION` with eligibility4/4 under the
frozen first-eligible rule. The selected falsifiable outline is
`CT002_FIXED_OPPONENT_MIX_CRITIC_CALIBRATION_DISTRIBUTION`:a later matched experiment
may change only critic-only calibration data distribution,self-play returns control
versus fixed opponent-mixture returns treatment,with actor frozen,equal critic updates
and identical subsequent PPO. It is distinct from EXP-W1,H2 and terminal KL/catch-up/
H11 loss experiments. Warm-critic evidence remains MIXED,H11 remains protocol-only
with no method-effect judgment,and exact H11 control quick5k remains -146.1726bb/100
with its registered gate failure;no prior critic method is reclassified PASS. FA002,
RS002 and LG003 were not evaluated after rank1 PASS and remain open. Latest formal V5
official100k remains -100.2475bb/100,CI95[-112.4067,-88.0883]. Result selection proves
no implementation,checkpoint or Slumbot improvement and no strength. Snapshot/ledger-
shard SHAs
9a486a396a424935f5346075585bd2bd9ce8966f34bbf5faa9b982722e121747 /
c011bba83c80ae2cc68d88c4cc8c5c16c13e8b98e10a3430415c0288ca2ef54e.
No CT002 preregistration,implementation,test,training,asset,GPU,checkpoint,evaluation
or Slumbot ran. Next later only is one fresh CT002 candidate-specific preregistration
plus independent preimplementation audit;stop before implementation or execution.
Behavior windows0;control/nonbehavior22;all four route families open;route exhaustion
false/unjudged;official hands this review0;L0;goal ACTIVE/incomplete.

The 2026-07-22 18:00 update below is historical registration evidence.

Current authoritative update (2026-07-22 18:00 EDT): canonical
SIMPLIFIED_ROUTE_REVIEW001 preregistration/audit SHAs
ed4162f6e45dea65cd65bd2e7273670ec947e76daf9d9941781cbdea075b493e /
a3141d43fd9b1767122210dc2157dca964e253e76f04b841d298193126d4e5c9
PASS35/35 are adopted without duplicate creation. Content-addressed identity/token
691b10aab0b6c812f92936e741e81af8142f3b730b3b7a04bd9c1168a33f15ac /
691b10aab0b6c812f92936e741e81af8 bind14 exact frozen inputs and a two-boundary
simplified workflow. A current-state rehash confirms all14 path/hash/byte triples exact
and both canonical atomic-result paths absent. Concurrent LG002 descendant CENSURE
96f0d5ccc80c673bd81d74533a9d303527805d1463f34fdb98d72e5af6520731
does not alter these frozen scientific inputs;all LG002 descendants remain authority
NONE and second recovery is forbidden. Frozen rank order is CT002 fresh critic/target
causal intervention,FA002 distinct CFR/BC warm-start,RS002 fresh play-time resolver,
then LG003 materially distinct non-recovery league. No candidate is selected yet.
Latest formal V5 official100k remains -100.2475bb/100,CI95[-112.4067,-88.0883];
latest externally screened H11 checkpoint quick5k remains -146.1726bb/100 and is
directional only. Last behavior change/screen remains H11;no behavior window has run
under DRIVE TO L5 v3. The immediate blocker is selecting the first eligible distinct
causal program without replaying terminal identities. Next later only is one atomic
reporting-only review result plus independent result audit using the14 frozen inputs;
stop before any candidate-specific registration,implementation,test,training,asset,
GPU,evaluation or Slumbot. Reconciliation snapshot/ledger-shard SHAs
11bcda8fc6cf4180bfb0d8b9c2c7176d7fb96da3dff4b89b3cc642fbc0e8ee61 /
1ae8ae57297bba35d5b2ba1e4c034fcfb1a95c1592d2897d36e4c3de31a8c457.
Behavior windows0;control/nonbehavior21;all four route families open;route exhaustion
false/unjudged;official hands this review0;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:56 update below is historical control evidence.

Current authoritative update (2026-07-22 17:56 EDT): a stale continuation created
LG002 recovery implementation descendants after the already-terminal 17:45 forbidden-
alternate-path CENSURE. Post-terminal descendant CENSURE SHA
96f0d5ccc80c673bd81d74533a9d303527805d1463f34fdb98d72e5af6520731
PASS20/20 binds trainer/launcher/test/audit-runner/result SHAs
9d42ff31a57c13ae8afd361b553fe9ea6e086c3e6d0c46328012f39b245b5310 /
c0d4999a4215cc1d130bcffef58a93185f21fe3f745f5e9e1509ef646cd3ddac /
c0fca59d4f64196d1f0beb1e481ff96af3a40a040683acb372308eb4fb3f0d83 /
5da053752d6017f7e02b92ee32b37ce24e6435bdb42d2536f126641815cc5cdf /
52de1d8fc7e78484c65ff2015a5473521dbe7d3d32037728565346d1f6ed5cde.
The self-reported implementation audit PASS35/35 and unit test PASS10/10 have authority
NONE because parent CENSURE SHA
78e46e590b349904f5019c69fd040100a62548040ff3cceae50f4ced97162f14
predates every descendant and had already set implementation/probe authority NONE.
Exactly two unauthorized zero-output probes ran(control_uniform,treatment_diversity);
both wrote0 files and initialized no GPU. Registered output root remains absent;no
training,checkpoint,evaluator,Slumbot or official hand ran. Preserve all descendant
bytes without delete,overwrite,repair,merge,reclassification or execution. Snapshot/
ledger-shard SHAs
14760ea564ab4b0c654ab99f980615a7648eae4737698dd55cb0f7d6016680a5 /
973015e6de8536b373861160bf736b4213fb3ba56958b9f7b751646f3eeec410.
Second recovery remains forbidden. Next later only is one simplified reporting-only
route-review preregistration plus independent audit selecting another ranked family or
a non-recovery league route;do not launch it automatically this boundary. Behavior
windows0;control/nonbehavior20;all four scientific routes open;route exhaustion false/
unjudged;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:45 update below remains the terminal parent and is historical context.

Current authoritative update (2026-07-22 17:45 EDT): the single LG002 recovery token
2320b32682e51ba0e3781407b92d3d75 is terminal
`LG002_RECOVERY_FAIL_CLOSED_FORBIDDEN_ALTERNATE_PREREGISTRATION_PATH_AFTER_AUDIT_NO_IMPLEMENTATION_NO_SECOND_RECOVERY`.
CENSURE SHA
78e46e590b349904f5019c69fd040100a62548040ff3cceae50f4ced97162f14
PASS22/22 binds canonical preregistration/audit SHAs
ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9 /
318899d0b0f1bfbfe80867473cf5ad192500379f6e8cc23479de22c9ef29bdec,
which had reported PASS100/100,before a later different-path,different-bytes file with
the same token appeared at SHA
9f04a6005ccd8802846a42120032691ac0219632380e3b1396eb961dfab026b9.
This violates the registered `alternate_path=FORBIDDEN` and
`same_basis_existing_different_bytes=TERMINAL_FAIL_CLOSED_NO_SECOND_RECOVERY` rules.
The canonical preregistration,audit,alternate file and unappended registration ledger
shard now have authority NONE;preserve without overwrite,merge,repair,reclassification
or descendant use. No implementation,probe,training,output,checkpoint,GPU,evaluator,
Slumbot or official hand ran;league science remains untested. CENSURE snapshot/shard/
main-ledger SHAs
607c935705c3a2cdbe5e4427712d09ca3ff060f70520d445b6770c3d642a8eef /
74f57fb63c6be5470446b261973cdecf669c6b437a1f7a54fe80e754b022c70c /
833b2e1c108dc45992e2ef67a8c2695283c38c56dc872536dbc49aec348bd466.
No second recovery is allowed. Next later only is a simplified reporting-only route
review preregistration plus independent audit to select another ranked family or a
non-recovery league route if supported. Stop before that review registration this
boundary and before any implementation or execution. Behavior windows0;control/
nonbehavior19;all four scientific routes open;route exhaustion false/unjudged;L0.

The 2026-07-22 17:41 update below is historical and its PASS100/100 has authority NONE.

Current authoritative update (2026-07-22 17:41 EDT): the single LG002 recovery is
registered and independently audited. Identity SHA/token
2320b32682e51ba0e3781407b92d3d750988f15dd2c8c03c0208ab61402cc29e /
2320b32682e51ba0e3781407b92d3d75 derive from
`LG002_RECOVERY|33a2f3f61007cb1b38ad8f4b8f93dd7d6f047f9b5cd8bbf55291a88e114e39a8`.
Preregistration/audit SHAs
ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9 /
318899d0b0f1bfbfe80867473cf5ad192500379f6e8cc23479de22c9ef29bdec
PASS100/100 bind current canonical bytes,15/15 frozen inputs and8/8 evaluation tools.
Independent read-only checkpoint inspection verifies model,optimizer,iteration35051,
576021901 hands,exact pool IDs109/115/120/129/103 and all five tensor state hashes;
H4 scores/weights were recomputed from raw edges. The sole arm behavior difference is
the conditional opponent weight vector;source/config/frozen pool/self-play0.20/
per-iteration assignment and SHA256 assignment U64 are common,with zero global RNG
consumption. Legacy H11 identity reuse is forbidden;future implementation must add an
opt-in mutually exclusive contract to actual `train_v5.py`,leaving defaults and network
unchanged. Stage A is matched5M control/treatment plus complete quick5k for both;Stage B
to20M treatment requires every frozen Stage A gate and has a15M quick5k interval.
Snapshot/ledger-shard SHAs
5057143fe4dbcf0f0625dba5e86343ed6023b2fbe0834a7ff2861591abee2668 /
ce92247cbf950efc795cff089ff1701bcaed173dc562142eabc495072bf6bbe8.
No implementation,test,training,output,checkpoint,GPU,evaluator,Slumbot or official
hand ran. The single recovery is consumed;second recovery forbidden. Next later only:
one implementation plus independent implementation audit and exactly two zero-output
probes;stop before training. Behavior windows0;control/nonbehavior19;all routes open;
route_exhausted=false/unjudged;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:35 update below is historical;its CENSURE remains immutable.

Current authoritative update (2026-07-22 17:35 EDT): LG002 token
cbfc90652e74dcc40e626669265dbd39 is terminal
`LG002_FAIL_CLOSED_SAME_CANONICAL_IDENTITY_DIFFERENT_PREREGISTRATION_BYTES_AUDIT_PREIMAGE_NO_LONGER_PRESENT_NO_SCIENTIFIC_TEST`.
CENSURE SHA33a2f3f61007cb1b38ad8f4b8f93dd7d6f047f9b5cd8bbf55291a88e114e39a8
PASS16/16 proves one canonical path held two different byte versions. The independent
audit SHA56b3de4e58f940715543ec7d6d8b03f311ae7074ab0d2fac20b493f5aaad10bb
binds earlier preregistration SHA/bytes
0c2dc68f3890145fa00ba934288c306b2eb04c144c2ac542e94a3e00c14d9400 /
26424,but the current path rehashes to
d8b7f30a06a1cbe443f04844d105cb957fe3091e4cc93ce4b7b3d3f04446ed6b /
23831. Neither byte version nor the unmatched audit has registration,implementation or
descendant authority. Preserve all current files and CENSURE without overwrite,merge,
repair or reclassification. No implementation,test,training,output,checkpoint,GPU,
evaluator,Slumbot or official hand occurred;the league hypothesis remains untested and
all four routes remain open. Snapshot/ledger-shard/main-ledger SHAs
d4d5bedcbd1fce3649b6be554884bd43b75e8accd2c6f0c50db8570b6734de03 /
7d637a465c6509c20ba471228249b1682e595dc949ebb06fc1fbcdc2005f29be /
05175d0fd3468b75de16c1a5cc481607648621d2f9c0b00c0eb5ff228096febd.
This pre-output control-plane collision qualifies for exactly one fresh corrected
identity without route review because the scientific design is unchanged. Next later
only:derive one token from `LG002_RECOVERY|<CENSURE SHA>` and create one fresh
preregistration plus independent preimplementation audit;stop before implementation.
If that recovery collides or fails control-plane,do not create another correction;
simplify or switch ranked family. Behavior windows0;control/nonbehavior18;official
hands0;route_exhausted=false/unjudged;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:22 update below is historical;WS002 selection remains immutable.

Current authoritative update (2026-07-22 17:22 EDT): WS002 is terminal
`WS002_PASS_SELECT_FRESH_ACTUAL_TRAIN_V5_OPPONENT_LEAGUE_IDENTITY_CANDIDATE_REGISTRATION_NEXT_ONLY`.
Canonical content-addressed result SHA
f431cb8e0b25a52e11faac6bb1148fb9f3538dbfda7cf3f53584a48690e58265
PASS47/47 embedded verification. The five preconditions passed:preregistration/audit
SHAs1a98009e22cee92a60a69755dbaabbfee7ab40ce45cc0feeb1041406bc635830 /
49d4e3440f0a93d830c9b8a414bb96d6f2c60b7eb1480cd178da8dad81752c6a
remain exact PASS64/64;all6 direct and22 nested frozen inputs rehash exactly;the one
canonical result path was absent prewrite;and no behavior,training,asset,checkpoint,
GPU,Slumbot or official hand occurred since MR001. Frozen rank1
`FRESH_ACTUAL_TRAIN_V5_OPPONENT_LEAGUE_IDENTITY` passes7/7:LG001 failed structurally
before behavior and left its hypothesis untested;the exact H11 launcher invokes
`train_v5.py`;the H11 checkpoint/manifest remain exact;and current `train_v5.py` SHA
ebd766112fd1b2f7130542e5f15ebe1e02c01e79c0f3a302bfc6811932e32956 has the required
H11 interfaces,uniform per-iteration opponent selection and pool-snapshot retention.
Ranks2-4 were not evaluated after rank1 PASS;all remain open and route exhaustion is
false/unjudged. This reporting decision proves no league effect or strength and grants
no implementation/execution authority. Snapshot/ledger-shard/main-ledger SHAs
a93d75372bf187ad9d3238239d9b6f6f99bd5eaab5d2e28e84f906227aede7a7 /
75e9af9dca693c852aa64c1221ef3c06a1f3882dc90a259c884b5fc5f94737de /
23a14b0013da16c18af08a5560c93c4eabe641d0bb245919448c0fa4120e5234.
Next later only is one fresh LG002 actual-`train_v5.py` candidate-specific
preregistration plus proportionate independent preimplementation audit. It must freeze
the exact runtime/H11 common identities and isolate conditional opponent weights versus
existing uniform selection as the sole coherent behavior intervention. Stop before
implementation,test,training,GPU,evaluation,Slumbot or checkpoint. Behavior windows0;
control/nonbehavior boundaries17;official hands0;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:16 update below is historical;its WCSR001 CENSURE remains immutable.

Current authoritative update (2026-07-22 17:16 EDT): WCSR001 late-duplicate CENSURE
SHA0f816cc2b06e2307b9402375efdc1cc7fc5f26a4f46e57a59fd59965024fe4f2
PASS12/12 preserves earlier content-addressed WS002 token
23dfd356983aa4607683808ee9d9a11c preregistration/audit SHAs
1a98009e22cee92a60a69755dbaabbfee7ab40ce45cc0feeb1041406bc635830 /
49d4e3440f0a93d830c9b8a414bb96d6f2c60b7eb1480cd178da8dad81752c6a
PASS64/64 as sole workflow-simplification successor authority. WS002 registration,
audit and snapshot completed before later random-token WCSR001 ce008ad8ef814daa965166a610eda204
preregistration/audit SHAs
0c79912a9d84526aaa1c9573013500ca66c7eb040db176259752ea73d9e4ca29 /
667c302f0d38484a49e4a3ee9cd259a1910e2ea1605c1c8256d53c34151c538f
reported PASS178/178. The late pair duplicates the same MR001 workflow function but
does not use the required deterministic content-addressed identity. It and every
result,audit,candidate or implementation descendant are authority NONE;preserve but
never merge,repair,rerun or extend. CENSURE snapshot/ledger-shard/main-ledger SHAs
e77296ccb56c4d72e48cd0794c2f65cea1552f02771983d7b535806f9e90bd95 /
abdb63ec0f437a5ef2c5a406cc485627f684c07f603044bd4864de5a806a10f5 /
ec3119fdfd5f89b27ca7362160661915d93e62c80ea3ba4f3621924cfac248fd.
No WS002 result,candidate registration,implementation,test,training,asset,checkpoint,
GPU,evaluator,Slumbot or official hand ran. Next later only remains one deterministic
atomic WS002 direct decision at its exact content-addressed result path with embedded
verification;stop before candidate-specific registration. Behavior windows0;
control/nonbehavior boundaries16;all four families open;route_exhausted=false/unjudged;
L0;goal ACTIVE/incomplete.

The 2026-07-22 17:12 update below is historical except that WS002 remains the sole
authoritative registered successor.

Current authoritative update (2026-07-22 17:12 EDT): WS002 content-addressed
preregistration/audit SHAs
1a98009e22cee92a60a69755dbaabbfee7ab40ce45cc0feeb1041406bc635830 /
49d4e3440f0a93d830c9b8a414bb96d6f2c60b7eb1480cd178da8dad81752c6a
PASS64/64 establish
`WS002_CONTENT_ADDRESSED_PREREGISTRATION_AUDIT_PASS_DIRECT_DECISION_RESULT_NEXT_LATER_ONLY`.
Identity SHA/token
23dfd356983aa4607683808ee9d9a11cb3633581168a78429b2cfed2e1f30afd /
23dfd356983aa4607683808ee9d9a11c derive deterministically from the terminal MR001
result SHA;registration and audit contain no random nonce,PID or creation clock. Six
direct inputs and22 nested MR001 inputs rehash exactly. Same basis must converge on the
same canonical path/bytes;alternate-named WS002 files are provenance only and global
path census is forbidden as a gate. Workflow is reduced to this registration/audit and
one later atomic direct decision with embedded verification,no separate result audit,
correction or version chain. The later decision preserves MR001's four-family rank and
eligibility rules;expected selection is not yet a result. Snapshot/ledger-shard SHAs
09a9b90090d562c687a7567e822b04ab5091f17d4b6e0d3a6b82784773619694 /
7d0d92b50d6467b31ab207e5549c51813a0c6f76eaf745763063140b7106b17c.
No WS002 result,candidate registration,implementation,test,training,asset,checkpoint,
GPU,evaluator,Slumbot or official hand ran. Next later only:one deterministic atomic
WS002 direct decision at the exact content-addressed result path with embedded
verification;stop before candidate-specific registration. Behavior windows0;
control/nonbehavior boundaries15;all four families open;route_exhausted=false/unjudged;
L0;goal ACTIVE.

The 2026-07-22 17:05 update below is historical except for terminal MR001 evidence.

Current authoritative update (2026-07-22 17:05 EDT): MR001 atomic result/audit SHAs
3a16b12b459f61be4dc8c0468553ec9a1a6bcf0b587da9d6f05395399f4b4bdd /
33f5ae48297852425aaab8f2b9a0dfb71b436e510560974ac297b110f3a25fce
PASS52/52 establish
`META_ROUTE_REVIEW001_FAIL_CLOSED_PREWRITE_ALTERNATE_REGISTRATION_PATH_NO_SELECTION_NO_ROUTE_JUDGMENT`.
All22 frozen path/hash/byte triples matched,but registered prewrite passed5/6 and
failed literal `NO_ALTERNATE_META_ROUTE_REVIEW001_REGISTRATION_OR_RESULT_PATH`:
the CENSUREd edc481 registration remains a physical alternate path. CENSURE can
preserve the earlier chain's scientific authority but cannot make the path absent or
waive an immutable gate. Candidate evaluation never started;candidate,family and rank
are null. This is control-plane evidence only and supplies no league,critic/target,
teacher,resolver,method,behavior or strength inference. MR001 is terminal with no
repair,rerun or alternate result path. Snapshot/ledger-shard/main-ledger SHAs
e5c32ef0ada94adcdd1384a791d9b91381bcbf308d0fd8aaa7527edd15290d47 /
82c5d7cbc7614c79712f0ccd112ca6cf4d19dfec21c891428e4ec64346caec15 /
3beea4e724f5ce4c14829f65073f06bc4d7e42417cc3b212e4781a042b75d451.
No candidate registration,implementation,test,training,asset,checkpoint,GPU,evaluator,
Slumbot or official hand ran. Next later only:one separately registered workflow-
simplification review plus proportionate audit defining a collision-safe direct
decision;stop before its result or any candidate program. Behavior windows0;
control/nonbehavior boundaries14;all four families open;route_exhausted=false/unjudged;
L0;goal ACTIVE.

The 2026-07-22 17:00 update below is historical except for immutable CENSURE provenance.

Current authoritative update (2026-07-22 17:00 EDT): MR001 late-duplicate CENSURE
SHA6b3d110a449b812057354270b314ab0d47bf0dbbbfd8bda4c467963beb81da59
PASS8/8 preserves the earlier-complete token519236e85ed44afba11b518aac271c47
preregistration/audit SHAs
162609df6244ace17daff6ec7ab0d5f935cbb452adcbd3ef332f4ca8db5ab3cb /
e9509e182783ee13a3599eec09435d65a023b60d3134057716a47bc89ec167aa
PASS153/153 as the sole MR001 authority. That audit completed with zero alternates before
the later token edc481c357d341a1b8335cb2ca08e469 registration/audit SHAs
ffe338142ca58b1ff680f0094cb93063d0aaa80e581140e252e36440b0d4b422 /
4f60ed8d241cbc3fb0b5d143a3ea9a3b3f98db9d60f06b83d92262bc81904d42
were created. The later chain,its snapshot and ledger shard are authority-NONE
provenance;never merge,repair,rerun,extend or create a result/descendant from it.
CENSURE snapshot/ledger-shard SHAs
b8964a99968956e351788154e6657579ea1e79b31e53417691ce4b5299a161b7 /
4e70c9768d02ff2613fc8e0a0085eabdcffe701a9966399c3667eabf875ffd7a.
No MR001 result/result audit,implementation,training,checkpoint,GPU,evaluator,Slumbot
or official hand exists. Next later only remains one atomic collision-checked
reporting-only result plus independent result audit using solely the earlier519236
frozen inputs/rules;stop before selected-program registration or implementation.
Behavior windows0;control/nonbehavior boundaries13;route_exhausted=false/unjudged;
L0;goal ACTIVE.

The 2026-07-22 16:55 update below is historical except for the earlier519236 frozen
registration/audit contract.

Current authoritative update (2026-07-22 17:05 EDT): META_ROUTE_REVIEW001 result/
audit SHAs
3a16b12b459f61be4dc8c0468553ec9a1a6bcf0b587da9d6f05395399f4b4bdd /
33f5ae48297852425aaab8f2b9a0dfb71b436e510560974ac297b110f3a25fce
PASS52/52 establish
`META_ROUTE_REVIEW001_FAIL_CLOSED_PREWRITE_ALTERNATE_REGISTRATION_PATH_NO_SELECTION_NO_ROUTE_JUDGMENT`.
All22 frozen path/hash/byte triples match and5/6 registered prewrite gates pass. The
literal `NO_ALTERNATE_META_ROUTE_REVIEW001_REGISTRATION_OR_RESULT_PATH` gate fails
because late CENSUREd token edc481c357d341a1b8335cb2ca08e469 preregistration still
physically exists. CENSURE preserves the earlier519236 scientific authority but cannot
make the alternate path absent or waive the immutable gate. Candidate evaluation did
not start;candidate,family and rank are null. MR001 is terminal with no repair,rerun,
alternate result or selection inference. All four families remain scientifically open
and route_exhausted=false/unjudged. Snapshot/ledger-shard/main-ledger SHAs
e5c32ef0ada94adcdd1384a791d9b91381bcbf308d0fd8aaa7527edd15290d47 /
82c5d7cbc7614c79712f0ccd112ca6cf4d19dfec21c891428e4ec64346caec15 /
3beea4e724f5ce4c14829f65073f06bc4d7e42417cc3b212e4781a042b75d451.
No candidate registration,implementation,test,training,asset,checkpoint,GPU,evaluator,
Slumbot or official hand ran. Next later only:one separately registered reporting-only
workflow-simplification review defining a collision-safe direct decision without
repairing or rerunning MR001;stop before its result or any candidate-specific work.
Behavior windows0;control/nonbehavior boundaries14;L0;goal ACTIVE/incomplete.

The 2026-07-22 17:00 update below is historical except for immutable duplicate-CENSURE
provenance.

Current authoritative update (2026-07-22 17:00 EDT): META_ROUTE_REVIEW001 late
duplicate CENSURE SHA
6b3d110a449b812057354270b314ab0d47bf0dbbbfd8bda4c467963beb81da59
PASS8/8 preserves the earlier-complete token519236e85ed44afba11b518aac271c47
preregistration/audit SHAs
162609df6244ace17daff6ec7ab0d5f935cbb452adcbd3ef332f4ca8db5ab3cb /
e9509e182783ee13a3599eec09435d65a023b60d3134057716a47bc89ec167aa
PASS153/153 as sole MR001 authority. That pair completed at20:53:22Z before later
token edc481c357d341a1b8335cb2ca08e469 registration/audit SHAs
ffe338142ca58b1ff680f0094cb93063d0aaa80e581140e252e36440b0d4b422 /
4f60ed8d241cbc3fb0b5d143a3ea9a3b3f98db9d60f06b83d92262bc81904d42
reported PASS58/58 and existed. The late pair omitted the already-complete alternate,
uses a different candidate order and result contract,and is authority NONE provenance.
Never merge,repair,rerun,extend or produce its result/descendants. CENSURE snapshot,
ledger-shard and main-ledger SHAs
b8964a99968956e351788154e6657579ea1e79b31e53417691ce4b5299a161b7 /
4e70c9768d02ff2613fc8e0a0085eabdcffe701a9966399c3667eabf875ffd7a /
f269669c8b059a59c9d8899857e5590c3c3dc77e10c4bfb8e0728831476e2fad.
No MR001 result,implementation,test,training,asset,checkpoint,GPU,evaluator,Slumbot
or official hand ran. Next later only remains one atomic collision-checked reporting-
only result plus independent result audit using only the earlier519236 frozen inputs
and rules;stop before candidate-specific registration or implementation. Behavior
windows0;control/nonbehavior boundaries13;route_exhausted=false/unjudged;L0;goal
ACTIVE/incomplete.

The 2026-07-22 16:55 update below is historical except that the earlier519236 pair
remains the sole authoritative MR001 registration.

Current authoritative update (2026-07-22 16:55 EDT): META_ROUTE_REVIEW001 token
519236e85ed44afba11b518aac271c47 preregistration/audit SHAs
162609df6244ace17daff6ec7ab0d5f935cbb452adcbd3ef332f4ca8db5ab3cb /
e9509e182783ee13a3599eec09435d65a023b60d3134057716a47bc89ec167aa
PASS153/153 establish
`META_ROUTE_REVIEW001_PREREGISTRATION_AUDIT_PASS_REPORTING_ONLY_RESULT_NOT_AUTHORIZED_THIS_BOUNDARY`.
The review is triggered by immutable LG001 structural failure/audit SHAs
074e937565b8015ea5bb05e4a77e81b27003dba14d1c8d2d2de721851ce0a87a /
665bbccbcf5fa8d1a635cbdaa262c56c40dcdfd5f1e84a86129d20c7de95e5f2
PASS50/50. It freezes22 exact direct inputs and ranks: (1) a fresh actual
`train_v5.py` opponent-league identity, (2) critic/target correction, (3) CFR/BC
distillation warm-start, (4) play-time resolver. Current train_v5 SHA
ebd766112fd1b2f7130542e5f15ebe1e02c01e79c0f3a302bfc6811932e32956
is reporting evidence only and must be freshly frozen by any later selected design;
historical H11 froze train_v5 SHA
98fe394c4d7b9338faa05abfbdf59015b4b0114cc8567f366cbda445a9afd19a.
H4 remains INCONCLUSIVE/no-candidate,PCV019 remains forbidden-training smoke only,
and H5 remains six gates short. The registration therefore supplies no scientific
selection or launch authority. Snapshot/ledger-shard/main-ledger SHAs
f1f5b03c76d2ca36905deb7f9817b0a0ed45f84eea2f5e533c5d74ecc099915f /
e767f5408e5870a328ed704c689314c647f1950262f31d9beb95c721ff7c0c8e /
2bc0d20111faf87675c24bce8b043922d70115537d6725a91758aefb6ba98dbf.
No review result,implementation,test,training,checkpoint,GPU,evaluator,Slumbot or
official hand ran. Next later only:one atomic collision-checked reporting-only
META_ROUTE_REVIEW001 result plus independent result audit from the frozen inputs and
rules. Stop before selected-candidate design implementation or launch. Behavior
windows0;control/nonbehavior boundaries12;route_exhausted=false/unjudged;L0;goal
ACTIVE/incomplete.

The 2026-07-22 16:49 update below is historical except for the immutable LG001
structural failure and authority-NONE descendant rule.

Current authoritative update (2026-07-22 16:49 EDT): LG001 preimplementation
trainer-identity failure/audit SHAs
074e937565b8015ea5bb05e4a77e81b27003dba14d1c8d2d2de721851ce0a87a /
665bbccbcf5fa8d1a635cbdaa262c56c40dcdfd5f1e84a86129d20c7de95e5f2
PASS50/50 establish
`LG001_FAIL_CLOSED_PREIMPLEMENTATION_REGISTERED_TRAINER_NOT_H11_RUNTIME_AND_COMMON_CONFIG_UNREPRESENTABLE_NO_VALID_IMPLEMENTATION_OR_LAUNCH`.
LG001 froze `train_v5_hybrid_h1.py` SHA
d64e5e907a9066357980fa59dd0029dc4b7436e4e9ca63ce537a81775595f9d1,
but immutable H11 launcher SHA
676f6696f6955a1248c9451a60653c161b9bee2f069627f39d7b1eedaa72b5a3
actually invoked `train_v5.py`,frozen by H11 at SHA
98fe394c4d7b9338faa05abfbdf59015b4b0114cc8567f366cbda445a9afd19a.
H11 requires PPO target-KL0.03,H8 value-head catch-up and H11 MSE catch-up semantics.
The registered base lacks those runtime interfaces and does not pass target-KL into
PPO. Adding league assignment there changes more than the frozen opponent-weight
variable;changing `train_v5.py` violates the frozen implementation path/SHA. This is
a structural design failure,not an eligible one-shot control-plane correction.

Same-boundary trainer SHA91a98cec...d5591,test SHAe72817e8...3686 and any later
descendant are authority-NONE provenance. After the terminal failure/audit,a late
implementation-audit descendant SHA
3c08a0de48fc9a79654fb65743f0480b4583c6d72cf58654c0bf88faa8273b29
reported PASS53/53 and zero-output contract tests against the structurally ineligible
trainer. The earlier failure audit's explicit current-or-later-descendant clause makes
that report and launcher SHA d858cbb5...0b689 authority NONE;never rerun,repair or use
them for training. No output root,behavior window,training,checkpoint,GPU,evaluator,
Slumbot or official hand ran. Snapshot/ledger-shard SHAs
bebacb917119a662b2f97da41d58fdee3631b0bf69db9253f75adf33e97a506b /
6172fff98f260e2d0f7028f49273b66f65c8cc14e41ce9751d37315d9955094d.
LG001 science is untested and the league route remains open. Next later only:one
simplified reporting-only meta-route review preregistration plus proportionate audit
choosing a fresh actual-`train_v5.py` league identity or a different hypothesis family;
stop before result,implementation,test,training or evaluation. Authoritative contract
tests0;late authority-NONE diagnostic tests10/10. Behavior windows0;control/nonbehavior
boundaries11;route_exhausted=false/unjudged;L0;goal ACTIVE.

The 2026-07-22 16:46 update below is historical except for immutable registration and
duplicate-CENSURE provenance.

Current authoritative update (2026-07-22 16:46 EDT): LG001 duplicate-registration
CENSURE SHA840e898f2717ef5c5134f43a9a14a1f3c104e3e9066571ae8bb9cab7b774fa24
preserves the earlier tokenized preregistration/audit SHAs
2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125 /
92dd02a8770035c5698edcc7288d8d8ea214c1ce465c8b3ad0a5eb0d07e666e9
PASS91/91 under token5ee42cb09c534cb3a294be701e94047f as the sole LG001
registration authority. Both were complete before the later incompatible
preregistration/audit SHAs
6881da78f49633afbebdd73dc137961b4cfd81885f1dee745dce2c8c84b52067 /
4d8c41e6cb37e20b6d8a67eb21fa2b40b637088ed6cc2c8886f446d7d545e0d8
reported PASS100/100. The later pair falsely recorded zero alternate LG001
registrations and omitted the already-complete tokenized pair;it is provenance only
with authority NONE. Preserve all four files without mutation and never implement,
train,evaluate or create a successor from the later pair.

CENSURE snapshot/ledger-shard/main-ledger SHAs
aeb9e458541705ad85d3bfa1ee7f3411a41fab906cb6529abda7b1d2bd72c28a /
06270eb9bbe4c32cfd8d3f894010dd6fddc056ce26dc40d4b5cd7103bbfb75d3 /
956be18c9e76e15fac885a48dc83e0b316712dab028a4e8ebac859da958757c4.
No implementation,contract test,training,checkpoint,GPU training,evaluator,Slumbot or
official hand ran. Next later only remains the token-bound LG001 implementation plus
proportionate independent implementation audit and zero-output deterministic contract
tests from the earlier authorized pair;stop before training. L0;goal ACTIVE/incomplete;
route_exhausted=false/unjudged.

The 2026-07-22 16:45 update below is historical except for the earlier tokenized
registration contract restated above.

Current authoritative update (2026-07-22 16:45 EDT): fresh LG001 unified behavior-
window preregistration/audit SHAs
2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125 /
92dd02a8770035c5698edcc7288d8d8ea214c1ce465c8b3ad0a5eb0d07e666e9
PASS91/91 establish
`LG001_REGISTERED_UNIFIED_WINDOW_AUDIT_PASS_IMPLEMENTATION_NEXT_ONLY` under token
5ee42cb09c534cb3a294be701e94047f. The audit independently rehashed16/16 valid
pre-RR033 inputs,the exact H11 source SHA
96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13
at iter35051/576,021,901 hands,its optimizer and five pool state hashes,recomputed all
H4 active-member diversity scores/weights,compared the H11 training config,and proved
all future code/output/evaluation-token paths absent. Singleton-adoption SHA
23bfa84b6ed1975a7e549f0fac54f6e7d090848633572ed154c56eb20cab2e0d
is compatible and only confirms CENSURE11a155... as sole authority;neither RR033 result
is entry authority.

LG001 is one same-start causal window. Stage A sequentially trains a uniform-control
and diversity-treatment for nominal5M hands each from the exact same checkpoint,
optimizer,deal stream,frozen five-member pool and V5/PPO configuration. Both keep
self-play0.20;only conditional pool weights differ. Control is0.20 each. Treatment
weights are ID103=.151331630996897,109=.272679451627751,
115=.062503368673781,120=.325118010944971,129=.188367537756600,derived prospectively
from mean absolute H4 common-deal edge bb/100. Pool mutation is disabled in both arms.
Both Stage-A endpoints require complete greedy-direct Slumbot quick5k bundles.

Stage B may continue treatment only to20M total if treatment exceeds both same-start
control and historical H11 by>=20bb/100,exceeds -126.1726bb/100,and greedy postflop
raise+all-in is<=0.80. Stage B also requires quick5k;20k registration is allowed only
if quick5k>+25bb/100 with the mechanism gate and complete bundle. Quick5k is directional
only and no strength claim follows.

Snapshot/ledger-shard SHAs
ce2639594e2c332c1eb6a368d3a6c44b92b82f25e8e61779a3afcb6e3c585c47 /
e921c798e3c00440a0627f37f4b549c73f85b1a210f5c8962b1fb4f31d390040.
No implementation,contract test,training,checkpoint,GPU,evaluator,Slumbot or official
hand ran. Next later only:opt-in LG001 implementation in the actual V5 trainer plus
proportionate independent implementation audit and zero-output deterministic contract
tests;stop before training. Latest official/external evidence remains unchanged,L0;
behavior windows0,control/nonbehavior boundaries9;all four families open;
route_exhausted=false/unjudged;goal ACTIVE/incomplete.

The 2026-07-22 16:18 update below is historical except for its immutable RR033
CENSURE/singleton provenance.

Current authoritative update (2026-07-22 16:18 EDT): singleton-adoption SHA
23bfa84b6ed1975a7e549f0fac54f6e7d090848633572ed154c56eb20cab2e0d
resolves two defensive RR033 CENSURE chains. The earlier-complete CENSURE SHA
11a155c5e158cc175e9203d2fd68e4e35df3e07f427bc2be1cb19e30f3b94599
is the sole authority. Later duplicate SHA
d6eb1462e1cfd034d53834ca47640226652593966143eefdc11b21dbcc938a41,
its shard and snapshot are provenance only with no additional governance or successor
authority. RR033 remains terminal fail-closed:both atomic-result hashes,the reported
LG001 selection and route judgment have authority NONE;no result repair,rerun,
reclassification,reconstruction,separate audit,alternate path or correction chain.

Next later only is one fresh unified LG001 behavior-window preregistration plus
proportionate independent audit from the active DRIVE TO L5 goal and direct rehashes of
valid pre-RR033 evidence. Neither censured result is entry authority. Stop before
implementation or execution. Implementation,training,checkpoint,GPU,evaluator,
Slumbot and official-hand authority remain NONE;official hands0;L0;route exhaustion
false/unjudged;goal ACTIVE/incomplete. Ledger after the singleton correction is SHA
3a0a4589ec9d2f756573e8e702e3dcf3dc867709cb3a286a24c2de319500a637.

The 2026-07-22 16:16 update below is historical except where restated above.

Current authoritative update (2026-07-22 16:16 EDT): RR033 canonical atomic-result
path held two distinct complete contents. First observed SHA
67b7048e793f708189d47f28f13279ebfc0e883a8b54c86965388117d1ea8e89,
8257B,reported PASS34/34,was bound by pre-overwrite snapshot/ledger SHAs
421041a166de3a20c0cd90bd37520a6a1a3300b82d5cf98b81b2d79e2398e446 /
4203273492315ecca2d29b7129ae7a3e61e1a7dce547076d155426d2304471b4.
The same path later stabilized at SHA
58e31f5632482789647b4741b1d4607169255e50cb0bf72022aea0eccf94a303,
14474B,reported PASS55/55. Both claimed prewrite absence and both reported LG001,so
agreement cannot restore single-writer immutable identity. CENSURE SHA
11a155c5e158cc175e9203d2fd68e4e35df3e07f427bc2be1cb19e30f3b94599
establishes
`RR033_ATOMIC_RESULT_CANONICAL_PATH_CONCURRENT_OVERWRITE_FAIL_CLOSED_BOTH_CONTENTS_AUTHORITY_NONE`.
Preserve the current file;never restore,repair,rerun,reclassify,audit separately,create
a correction chain or alternate RR033 result path. RR033 selection and route judgment
authority are NONE;preregistration/audit remain registration-only evidence.

This is control-plane failure only:no method,behavior or strength inference and no
implementation,training,checkpoint,GPU,evaluator,Slumbot or official hand ran. To
honor the workflow simplification guard,do not add another route review. Next later
only is one fresh unified LG001 behavior-window preregistration plus proportionate
independent preregistration audit under the active DRIVE TO L5 goal. It must independently
rehash valid pre-RR033 H4/H5/PCV019/warm-critic/trainer evidence,not use either censured
result as entry authority,and freeze exact source lineage,implementation,league
members/weights,training bounds,checkpoint eligibility and mandatory complete
greedy-direct quick5k. Stop before implementation or execution.

Censure snapshot/ledger-shard SHAs
31d2aa8c0ab59c67942f614a527a200b2b5d51ee8d7e963fe8f4ea2747845176 /
d0295f19c512a403901b22a0a3866971f9ec769d562bc25ced3728b6db097c5d.
Latest valid official remains20,400 hands,-140.151bb/100,CI95 lower -178.386,L0;
last complete external screen remains CAL-EXT-002 H11 iter35051/576,021,901,
checkpoint SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,
quick5k -146.1726bb/100,CI95[-238.5979,-53.7473]. Behavior windows=0;
control-plane/nonbehavioral boundaries=8;all four families remain open;
route_exhausted=false/unjudged;goal ACTIVE/incomplete.

The 2026-07-22 16:09 update below is historical and its RR033 result authority is
CENSUREd by the update above.

Current authoritative update (2026-07-22 16:09 EDT): Route Review033 atomic result
SHA67b7048e793f708189d47f28f13279ebfc0e883a8b54c86965388117d1ea8e89
PASS34/34 establishes
`ROUTE_REVIEW033_PASS_SELECT_LG001_OPPONENT_LEAGUE_BEHAVIOR_WINDOW_ROUTE_NOT_EXHAUSTED`.
It rehashed all16 frozen inputs and selects
`LG001_V5_DIVERSITY_WEIGHTED_OPPONENT_LEAGUE_BOUNDED_BEHAVIOR_WINDOW`:replace only
the training opponent-selection distribution with a frozen diversity-weighted league,
while preserving the model,objective,optimizer,action and observation contracts. The
first checker invocation stopped pre-judgment on CP950 decoding and wrote no output;
the UTF-8-corrected full rerun passed34/34 without changing registration or inputs.
There is intentionally no separate result audit or correction chain.

Scientific basis:H4 exhausted only its loss-kbest snapshot-inversion rule,not dynamic
or diversity-weighted leagues;the trainer already supports normalized opponent mixes
and per-game sampling. Critic/target remains open but previously exercised;the teacher
method remains open although the TN001 qualification leg is control-plane closed;the
resolver remains prerequisite-limited by six gates. Thus all four non-V6 families are
unexhausted and route_exhausted=false/judged. Result pre-refresh snapshot/ledger-shard
SHAs421041a166de3a20c0cd90bd37520a6a1a3300b82d5cf98b81b2d79e2398e446 /
4203273492315ecca2d29b7129ae7a3e61e1a7dce547076d155426d2304471b4.

Next later only:one unified LG001 behavior-window preregistration freezing the exact
source checkpoint/lineage,implementation,frozen diversity weights and eligible league
members,training bounds,checkpoint eligibility,and a mandatory complete greedy-direct
Slumbot quick5k for every eligible checkpoint and no later than20M training hands. No
intervening route review. Stop before implementation or execution. Quick5k is
directional only;20k and formal100k require separate gates. No behavior change,
implementation,training,checkpoint,GPU,evaluator,Slumbot or official hand ran.

Latest valid official remains20,400 hands,-140.151bb/100,CI95 lower -178.386,L0.
Last external screen remains CAL-EXT-002 H11 iter35051/576,021,901,checkpoint
SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,
quick5k -146.1726bb/100,CI95[-238.5979,-53.7473]. No-progress behavior windows=0;
consecutive control-plane/nonbehavioral boundaries=7;goal ACTIVE/incomplete.

The 2026-07-22 15:52 update below is historical.

Current authoritative update (2026-07-22 15:52 EDT): reporting-only Route Review033
preregistration/audit SHAs
e8d420cbf0494e9686505c31e5f5c5c507a66fc05568f98dc5c89bf007d61b03 /
80a86d77879663503b7396f677220946a24090b729da940477f1d0e3f5f24d4b
PASS57/57 establish
`ROUTE_REVIEW033_REGISTERED_REPORTING_ONLY_AUDIT_PASS_ATOMIC_RESULT_LATER_ONLY`.
The audit rehashed16/16 inputs. RR033 closes the TN001 qualification leg only for
control-plane authority;the teacher method remains scientifically untested. H4 closes
only its loss-kbest excluded-snapshot inversion rule,not the wider opponent-league
family;H5 resolver still lacks six readiness gates;critic/target has direct anchor-KL
mechanism evidence but has already been behaviorally exercised. Frozen order is LG001
diversity-weighted opponent league,CT001 anchor-KL schedule,a distinct non-TNQ teacher
route,then full200 resolver. With inputs unchanged the later result is expected to
select LG001.

Workflow is simplified to one later canonical deterministic RR033 atomic result with
embedded source/decision checks. No separate result audit,mutex,result correction chain
or intervening review is allowed. A valid selection directly authorizes one unified
behavior-window preregistration freezing implementation,training bounds,checkpoint
eligibility and mandatory complete greedy-direct quick5k;quick5k remains directional
only and must occur for every eligible checkpoint and no later than20M training hands.
No RR033 result,implementation,training,checkpoint,GPU,evaluator,Slumbot or official
hand ran. Snapshot/ledger-shard SHAs
05e5156233ed64cf4d41d20212ab70c4579c275862e23cffdad911dd33e57a23 /
06af1ab9c938bde7f2770c3385bc28dc556e55abb50bfaa272a4eea9ffc3af4f.
Next later only:write the single canonical RR033 atomic result,then stop.

Latest valid official result remains20,400 hands,-140.151bb/100,CI95 lower -178.386,
L0. Last external screen remains CAL-EXT-002 H11 iter35051/576,021,901,checkpoint
SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,
quick5k -146.1726bb/100,CI95[-238.5979,-53.7473]. No behavior changed. Ranked
hypothesis before result is opponent league;the blocker is the RR033 atomic judgment
before a direct behavior window. Next external trigger is the first eligible selected
window checkpoint. No-progress behavior windows=0;consecutive control-plane or
nonbehavioral boundaries=6. All four non-V6 families remain scientifically unexhausted;
route_exhausted=false/judged;goal ACTIVE/incomplete.

The 2026-07-22 15:42 update below is historical.

Current authoritative update (2026-07-22 15:42 EDT): TNQ002 clean registration is
terminal
`TNQ002_CLEAN_REGISTRATION_SINGLETON_ADOPTION_COLLISION_FAIL_CLOSED_NO_IMPLEMENTATION_NO_SECOND_CORRECTION`.
Two independent writers adopted the same detached mutex holder,nonce
d242df102dce415ea01b7a0ef30c21f0 and PID38532 but created distinct registration
chains. Chain A prereg/audit SHAs
8529e95c7fe971be25b8dc6286418c8279ccb46870d53792bff8ab25ec5a7201 /
67129cb8bfecfa235fa0f90c544a0273e53d8fb1db3c7608c359fe509542557e
reported PASS71/71;chain B SHAs
730d61cb3123d7cebcf5ce2a21fe347ae42a5d034fec5d609c2c98bb032777f9 /
422687a700613937448751b208757bae47c09b24dd5989fd8fdb98f0bffd8fb1
reported PASS60/60. CENSURE SHA
2811ac11403a46c4e102a9ece98bc1ff6c0202d3591c5ec0cb81b98fc2e97ad5
assigns both authority NONE:the holder proved one mutex owner,not one identity-bound
registration writer or canonical path. Chain A c059 was false because chain B already
existed;chain B omitted chain A. Release SHA
0072ef8cdfb7e24d3d5ab64cf90d4ed45645c8cd3e6fb3f59bb7c637df3bb1a0
ended the holder;Python count0. No implementation,probe,qualification,row,rollout,
output,asset,model,training,GPU,evaluator,Slumbot or official hand ran. The single clean
correction attempt is consumed;no TNQ002/TNQ003 correction,implementation or
qualification is authorized. Snapshot/ledger-shard SHAs
fadf810ae242d7e8ff6af4dcc20dcd6c38d30b774ceec3f24b8a73b488ecad6f /
dc4c74c67cb49a98744165e02d51a74e6f791e5970bab391b09240aa2f8e0732.
Next later only is separately registered reporting-only Route Review033
preregistration plus independent preregistration audit to close this TN001 leg and
rerank remaining non-V6 families;stop before a review result or behavior work.

Latest valid official campaign result remains20,400 hands,-140.151bb/100,CI95 lower
-178.386,L0. Last complete external screen remains CAL-EXT-002 H11 iter35051 /
576,021,901,checkpoint SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13,
quick5k -146.1726bb/100,CI95[-238.5979,-53.7473]. No behavior changed. The exact-V5.5
trajectory-native teacher hypothesis was not scientifically tested;this specific TN001
qualification leg is closed by exhausted correction authority. Runtime qualification
therefore remains unobserved. Next external trigger remains the first eligible frozen
BC checkpoint. No-progress behavior windows=0;consecutive control-plane/nonbehavioral
boundaries=5. All four non-V6 families remain scientifically unexhausted pending
rerank;route_exhausted=false/judged;goal ACTIVE/incomplete.

The 2026-07-22 15:37 update below is historical and its PASS authority is CENSUREd.

Current authoritative update (2026-07-22 15:37 EDT): the sole clean TNQ002 collision
correction is registered under global mutex
`Local\CardPilot_TNQ002_CLEAN_REGISTRATION_SINGLETON`,nonce
d242df102dce415ea01b7a0ef30c21f0. Preregistration/audit SHAs
8529e95c7fe971be25b8dc6286418c8279ccb46870d53792bff8ab25ec5a7201 /
67129cb8bfecfa235fa0f90c544a0273e53d8fb1db3c7608c359fe509542557e
PASS71/71 establish
`TNQ002_CLEAN_COLLISION_CORRECTION_REGISTERED_AUDIT_PASS_IMPLEMENTATION_LATER_ONLY`.
The audit rehashed11/11 inputs and canonical authoritative-TN001 exact-interface,
24-witness,trajectory-native discovery,quality-gate and resource-contract blocks. The
qualification remains24 reached acting-player infosets across200/100/50bb,all four
streets and both actors;exact native V5.5 nine-slot identity;per-rollout hidden
resampling;two MC32 batches per native action;24 repeats;and300s/512MiB/64MiB
fail-closed bounds. Old CENSUREd TNQ001/TNQ002 scientific content is unused. All fresh
launcher,runner,result-auditor,implementation-audit and output paths are absent;no
implementation,probe,qualification,row,rollout,asset,model,training,GPU,evaluator,
Slumbot or official hand ran. Snapshot/ledger-shard SHAs
1258eef3c1349ef5a6006b3c26a3257f61a0ccb453b878ae0c659b094f333cd3 /
92a5da0c148778dce8cf79eeaf5c4a0f3ae2c25b92f1673f44eb23c19de14e7a.
Next later only is exact token-bound launcher/runner/result-auditor implementation plus
one proportionate independent implementation audit containing exactly two fresh
sequential launcher-bound zero-file child probes;stop before qualification.

Latest valid official campaign result remains20,400 hands,-140.151bb/100,CI95 lower
-178.386,L0. Last complete external screen is CAL-EXT-002 on frozen H11 iter35051 /
576,021,901,checkpoint SHA96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13:
quick5k -146.1726bb/100,CI95[-238.5979,-53.7473]. No behavior changed in TN001/TNQ001/
TNQ002. Ranked hypothesis remains exact-V5.5 trajectory-native CFR/BC teacher
warm-start;the blocker is runtime qualification of the24 reached infosets under hidden
resampling,MC32 quality and resource gates. The next external trigger is the first
eligible frozen BC checkpoint. No-progress behavior windows=0;consecutive control-plane
or nonbehavioral boundaries=4. Critic,target teacher,league and resolver families remain
open;route_exhausted=false/judged;goal ACTIVE/incomplete.

The 2026-07-22 15:25 update below is historical.

Current authoritative update (2026-07-22 15:25 EDT): two late same-turn TNQ002
descendants appeared on the already-CENSUREd nonce/path after the release boundary:
preregistration/audit SHAs
a217b6851a17ae8c71725b854ce6991eabf5850306b5f1122a608c3950bc24e3 /
cb8eeef827e8f4273e5b4ec37e66a2eb56cf15498562640b90613a153e3ed67c.
The audit reported PASS50/50 but was created after release while claiming the holder
alive,mutex held and release absent. Governing CENSURE SHA
00317b51b1d35f850c0df247016ef1ceccf28477d80404c9773eee351213c576
had already assigned every same-turn descendant authority NONE;late-descendant CENSURE
SHA d81b5af4f3c8b5423dc512d290f54569c9cf5dcde4983cb0126bee28a9d3c79a
therefore preserves both files as provenance only. The old nonce and all associated
registration/audit/lock/metadata/release paths are burned. No implementation,probe,
qualification,row,rollout,output,asset,model,training,GPU,Slumbot or official hand ran.
The single TNQ002 correction allowance remains unconsumed. One later clean boundary
may preregister and independently audit that same correction identity only,using a new
nonce and entirely fresh paths;no automatic successor and no second correction.
route_exhausted=false/judged;L0;goal ACTIVE/incomplete.

The 2026-07-22 15:12 update below is historical.

Current authoritative update (2026-07-22 15:12 EDT): TNQ001 is terminal
`TNQ001_FAIL_CLOSED_CONCURRENT_PREREGISTRATION_PATH_COLLISION_NO_IMPLEMENTATION_NO_SCIENTIFIC_ROWS`.
The immutable preregistration path was first observed complete at SHA
86cb798d861bcb1fc76beba94c3f4ff7efef1ee9ac84184d40183c3bb5bf8ab0,then changed in
place to SHA6fdbb1ca60a7a8517c0eee305f5d5c256b197fda1c79f836d41076a0a616df30
with a different schema,classification,length and contract. Final audit SHA
d47da4453e160c2beb5bef3648ff3a2d3eab1095fcd2e4d64bf0374783280a07 reported
PASS192/192 but checked only the final bound content and omitted the already-observed
collision. CENSURE SHA
dbdf87a4123a88b5deffc4836913d8a4c807cacd7d1273832548f1ecffed46fd gives the
preregistration,audit,derived snapshot and main-ledger PASS event authority NONE.
Preserve all files;never implement,probe,execute,repair,rerun or reclassify TNQ001.
Implementation/probes/qualification/rows/rollouts/output/assets/model/training/GPU,
evaluator,Slumbot/checkpoint/official hands are all0. Authoritative TN001 science is
unchanged,so the pre-output correction rule permits exactly one later fresh
`PHASE_FA_TNQ002_EXACT_V55_REACHED_INFOSET_MC32_BOUNDED_QUALIFICATION_COLLISION_CORRECTION`
preregistration plus proportionate independent audit with fresh paths/nonce and a
short-lived exclusive registration guard;do not create it automatically this turn.
route_exhausted=false/judged;L0;goal ACTIVE/incomplete.

A same-turn automatic TNQ002 lock start after that stop is CENSUREd by SHA
00317b51b1d35f850c0df247016ef1ceccf28477d80404c9773eee351213c576.
PID45836 acquired nonce b7ada48297594b26bc401e0a46f84656 lock/metadata SHAs
6c29cd93b3e8dc17345be71da83a2a7adeaf8ed794c2e07b3f04a6a96f8f4846 /
e005a0fd23370367f4a43ffd10891a38f858f5080229ec1f58c9ebc44485f3f5,but no
TNQ002 preregistration/audit or implementation existed. Release SHA
127d5b3e85aefbdce248485d093ee9a3e22219dbdf54ee26f2acee5eb47fbc91
was created;the holder exited and Python count returned0. Lock/metadata and any
same-turn descendant have authority NONE. The single correction remains unconsumed;
a later clean TNQ002 boundary must use a fresh nonce and fresh lock/metadata paths.

The 2026-07-22 14:59 update below is historical.

Current authoritative update (2026-07-22 14:59 EDT): fresh TN001 preregistration/audit
SHAs4be3af34448f7fa9bfba4af4e70d81f1e6d7b2cfd415ce1e93e1069033b20dc0 /
2ca9e69fccaa57d5e9a433aeedebbe9fe4f8379407daa71a3e0b49ac3cf47963
PASS135/135 establish
`TN001_REGISTERED_DESIGN_AUDIT_PASS_TNQ001_REGISTRATION_NEXT_LATER_ONLY`.
The design freezes24 finite witnesses covering200/100/50bb,all four streets and both
acting players through exact native9-slot replay;two independent MC32 batches per
native action;opponent-private and unrevealed-board resampling per rollout;actor
observation/action invariance;zero projection,drop,collision,renormalization or illegal
mass;and prospective300s/512MiB/64MiB fail-closed bounds. It uses only authoritative
WS001,the valid v2 registry,PCV019/PCV016,Revision003/Review004 and the three exact
protected inputs;all CENSUREd006/007/R1 content is excluded. Next later only is fresh
`PHASE_FA_TNQ001_EXACT_V55_REACHED_INFOSET_MC32_BOUNDED_QUALIFICATION`
preregistration plus proportionate independent preregistration audit,then stop. No
TN001 result,TNQ001 implementation/probe/qualification,asset,model,training,GPU,
evaluator,Slumbot or checkpoint;official hands0;route_exhausted=false/judged;L0;goal
ACTIVE/incomplete.

A late same-purpose TN001 prereg/audit created after the authoritative pair,SHAs
3dae3b32ec4af21ed41d6b14050f76e87b896ab07d4cbd54fc2a431ac1c50dd1 /
a0f2b992444482910eb6590473eee2967c67609e8bb37880433412d8b3d59423,have authority
NONE under CENSURE5ce8f0a2b37fe0290c0c4a9d63d60ec37207693e6dd3a939d2fc0221661dd43b.
Preserve as provenance only;never use its content or spawn a descendant. Authoritative
TN001 and the TNQ001-next boundary are unchanged.

The 2026-07-22 14:42 update below is historical.

Current authoritative update (2026-07-22 14:42 EDT): WS001 atomic adjudication SHA
eedcfb2fd71cfca88d68d551dc7f0e77d751bc57a29d0efc2c30a7c6568dc2c9
is terminal PASS with embedded10/10 deterministic checks and selects fresh
`PHASE_FA_TN001_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY`.
Under token31f2022c526a4c688a595720a70f8877 and short-lived mutex PID36576,it
rehashes33/33 registered references across30 unique paths,3/3 protected inputs and
canonical pair digest8f0c94bcd4c2138accfb7fa91accd543e6f8d178cc0e31428e3f0b1c626ea54e.
All five registered rank1 predicates pass:PCV019 exact-interface bounded smoke and zero
illegal mass;PCV016 exact semantic owners and no route-infeasibility proof;Revision003
global unreachable-quota failure;Review004 incomplete global-support census without
exhaustion;and exact action/transition/BC-anchor hashes. All four families remain open,
so route_exhausted=false/judged. There is intentionally no post-result audit under valid
WS001. Concurrent duplicate WS prereg/audit remain authority NONE under CENSURE
0fd53f71f021799a4223fa12b7036a06c3c5708a52ae356067a67fe5959ced5d.
Next later only is one fresh TN001 reporting/design preregistration plus proportionate
independent preregistration audit,then stop;no automatic TN001 result,implementation or
qualification. After result snapshot,append-only ledger and controls refresh,release
SHAf2bccf018a8344dfe6f8a9a62d4faf201862002c1010a4043dca06261499fe22
was written in the same turn;PID36576 exited and the mutex is absent. No behavior/model/training/GPU,evaluator,Slumbot or
checkpoint changed;official hands0,L0;goal ACTIVE/incomplete.

The 2026-07-22 14:36 update below is historical.

Current authoritative update (2026-07-22 14:36 EDT): workflow simplification WS001
prereg/audit SHAs97a253416d579e30ecb5b984b7f7c1d6d1f141409504301b20e4ea3c61892677 /
9930d3f60b97b5377e2b0fbbd246854a37eff7b6d596bd4b27b7d6b7d4b0e31c
PASS80/80 establish
`WS001_REGISTERED_AUDIT_PASS_ATOMIC_ROUTE_ADJUDICATION_LATER_ONLY`.
Concurrent later duplicate prereg/audit SHAs
298fa276a2dc0469607d65979b7c9a39423e741fd519314aa97bc2b711b12702 /
27f87be7ae083c4904deaaa8a654098275a7a8455d6af8802e9c4b8a59aaf2ff
have authority NONE under CENSURE SHA
0fd53f71f021799a4223fa12b7036a06c3c5708a52ae356067a67fe5959ced5d;
they were created after WS001 and may not spawn a result or support workflow,science,
selection or exhaustion. Preserve them as provenance only.
This is the required simplification after repeated control-plane closures. It removes
all new Route Review031/RR032 identities,a separate post-result audit,cross-turn
persistent mutexes,incompatible reuse of prewrite absence gates and auxiliary checker
chains. It retains the valid registry SHA971e080b...76cf4,33 registered references over
30 unique paths,3 protected inputs,the exact four-family exhaustion rule and candidate
order. Fresh token31f2022c526a4c688a595720a70f8877 binds one later result path and
one short-lived same-turn lock namespace;all four result/lock/metadata/release paths
are absent and scoped processes0. The later atomic result must embed deterministic
source rehashes and decision checks;there is intentionally no post-result audit for
this pure read-only reporting judgment under the current constitution. Any false check
fails closed with no retry. A valid rank1 maps only to fresh
`PHASE_FA_TN001_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY`,
never closed006/007/R1 identities. Stop registration-only:no atomic result now,no
scientific judgment,no implementation,pilot,asset,training,GPU,evaluator,Slumbot or
checkpoint. route_exhausted=false/unjudged,official hands0,L0;goal ACTIVE/incomplete.

The 2026-07-22 14:26 update below is historical.

Current authoritative update (2026-07-22 14:26 EDT): RR032-C1 is terminal
`RR032_C1_FAIL_CLOSED_REGISTERED_RESULT_AUDIT_LIVE_GATE_CONTRADICTION_NO_JUDGMENT`.
The sole read-only result SHA
3a2ca22d517a516eedd090d0b5333ccd87823c98421b347e82f64fda40fe3fb7
was created once after33/33 registered hash checks,3/3 protected inputs and all nine
pre-result lock gates passed. Independent audit SHA
477247cae341f4583bb543bfcae5ebbd692d76baae1e9be413858ab8c3663f63
is exact FAIL_CLOSED49/50. The sole failure is the immutable preregistration requiring
the audit to revalidate the same nine live gates while its ninth gate requires both
result and audit paths absent;after the mandated result exists this is impossible.
All result-content checks passed,but result,rank1 selection and route judgment have
authority NONE. This is control-plane contract evidence only,not scientific
falsification or family exhaustion. The one correction allowance is consumed;never
repair,rerun,reclassify or create a second correction. Next is a separately registered
workflow-simplification review only,which must remove self-contradictory live-state
contracts and decide the smallest direct scientific adjudication without another
Route Review031/RR032 checker chain. No automatic successor this turn. Release signal
SHA26c9dfde8119585688bfcc260384c764ccc378cce4e7318238f2894f1080a461
was written only after snapshot,append-only ledger and controls refresh;holder PID46804
exited and the named mutex is absent. No implementation,pilot,asset,training,GPU,evaluator,Slumbot
or checkpoint;route_exhausted=false/unjudged,official hands0,L0;goal ACTIVE/incomplete.

The 2026-07-22 14:17 update below is historical.

Current authoritative update (2026-07-22 14:17 EDT): RR032-C1 correction prereg/audit
SHAs e0c65b9103f57988790b78b8af0bd269796dd498fb7194a8eb2f617208525f32 /
e95399d3f193ca32fcc87130b9626ee356b4e5343acd811c4ce6cd9ffc3611ac
PASS152/152 establish
`RR032_C1_LOCKED_FRESH_PATHS_REGISTERED_AUDIT_PASS_RESULT_LATER_ONLY`.
This is the sole correction identity allowed by expanded collision CENSURE
1e7395b50d21350d68b5fc9da0b4802b146dd2fc2ad3b20c56cebbeaa5d2ceed;
the four-family scientific design,order,evidence and thresholds are unchanged and all
collided RR032 rank1 content remains authority NONE. Fresh nonce
ac4f8bee212240279ff54388fdc52158 binds a Windows named mutex plus exclusive lock and
metadata SHAs2dc64bc4640b981cc8121d38ceebb5b761b64c0242c1cd827ad614be668f3894 /
7a3529d28f37a21a8609a7806a4fde48b57b27eddbb59fc347f9ab55d806432a;
holder PID46804 is the sole scoped Python process and the mutex is observed held.
Release,result and result-audit paths are absent. Pre-refresh snapshot-manifest SHA is
to be recorded in the C1 ops status. Stop registration-only. A later boundary may write
exactly one C1 read-only result then one proportionate independent result audit under
the same continuously held lock;no automatic result now,no family/selection/exhaustion
judgment,no implementation,pilot,asset,training,GPU,evaluator,Slumbot or checkpoint.
route_exhausted=false/unjudged,official hands0,L0;goal ACTIVE/incomplete.

The 2026-07-22 14:09 update below is historical.

Current authoritative update (2026-07-22 14:09 EDT): RR032 result/audit SHAs
40e9ba39abffcf0283760c9ac99f3f7d22c0ba577f2d12d392fbf8b907aab2dd /
cad1e8de7a1bb2faebc29030af59219918589a5436ab5f01be5acc9509c1f390
reported rank1 selection and PASS136/136,but the active root and an already-running
continuation wrote the same result path concurrently. Expanded CENSURE SHA
1e7395b50d21350d68b5fc9da0b4802b146dd2fc2ad3b20c56cebbeaa5d2ceed
makes result,audit,derived manifest77115ceb...c6809 and the corresponding main-ledger
event authority NONE. Audit checks fresh-exclusive/result-created-once are false.

RR032 prereg/audit SHAsc424b7196adf7b0b27ff8a7b0c9225a0b0093f7ecb4ea57f4e259909eb37ade3 /
be9fb211e4fbd4fa45c6084f4875ae7f9b859ca4a4b895a7825ef1ad5045952b
remain PASS50/50 registration-only evidence,but result paths are terminal occupied and
there is no route selection or exhaustion judgment. Zero scientific rows,pilot rows,
model changes,training and hands classify this as a preoutput same-path control-plane
failure. Exactly one later fresh corrected identity may be preregistered without another
four-family review;it must use fresh absolute paths and an OS-level exclusive session
lock with fresh nonce held before preregistration through result audit. Stop here:no
automatic correction this turn,no CENSUREd rank1 content use,no implementation,pilot,
asset,training,GPU,evaluator,Slumbot or checkpoint. route_exhausted=false/unjudged,
official hands0,L0;goal ACTIVE/incomplete.

The reported 2026-07-22 14:04 result state is CENSUREd and omitted here.

The 2026-07-22 13:48 update below is historical.

Current authoritative update (2026-07-22 13:48 EDT): concurrent Route Review031 v9
prereg/audit SHAs3a7394da34485ac6b05948eeb8b2089d2f2f7168410fb5e7eb57e55fa261d892 /
301938d816f36858f6e67f4cf3f7448355789d093f7cdf400e544b81a1c99123
reported PASS80/80 but preceded and omitted the root-final v8 CENSURE. Root hard-stop
CENSURE SHA187d4e7f87222b305d3f44ba4b38d7515d15e3e0277fae5e0b7618fe1d7d037b
makes the v9 chain authority NONE;v9 result/audit absent.

Status is NO_AUTOMATIC_SUCCESSOR_REGISTRATION_RESULT_OR_CONTROL_REFRESH. Goal remains
ACTIVE but incomplete;route exhaustion false/unjudged;heartbeat DELETED,TOML absent,
Python0,official hands0,L0. Resume only in a new clean user or root session after
rereading this topmost state. Do not create another numbered route/design boundary,
pilot,asset,training,GPU,evaluator,Slumbot or checkpoint automatically.

The 2026-07-22 13:44 update below is historical.

Current authoritative update (2026-07-22 13:44 EDT): the drained stale continuation
wrote Route Review031 v8 prereg/audit SHAs
c01b0e45b36701e63d73e18ca012f9bb6a4695f0df5ed1ab9498c85c1c9c53ab /
113b90012c3bfda66ea3c12f2c308242d4e29e8731f3c341a2a4d6c1de25eb95,
reporting PASS110/110. Root CENSURE SHA
c81a095d1344074aebffa367d7402598c5a158dd40ca596f6b00d52516eca3e9
makes both authority NONE because they omitted the preexisting v7 result CENSURE and
overlapped root control refresh. v8 result/audit absent;v8 terminal with occupied
CENSUREd registration paths and no judgment. Heartbeat DELETED,TOML absent,quiet60s,
Python0,official hands0,L0. Next later only fresh Route Review031 v9 preregistration
plus independent preregistration audit with fresh paths and every CENSURE;no v9 result
same boundary. Stop here;do not create v9 automatically or launch any downstream work.

The 2026-07-22 13:38 update below is historical.

Current authoritative update (2026-07-22 13:38 EDT): an already-running heartbeat turn
wrote Route Review031 v7 result/audit SHAs
ea9df4fe614e271ebb6f1d709f75fc45d7271d4b22fb25509e0728b9880a60f0 /
96ccc0df00ba3b8c74cd4bef13ee4b383c3ce41405cc000d9af8e0fd1fefd3a4,
reporting PASS100/100. CENSURE SHA
575e916b73ef46b4e812ec1e5826f7096fd9c5060312d43f0dd367422d6c26a5
makes them authority NONE:the v7 registration prohibited result creation in that
boundary,the result overlapped root control refresh,and it omitted preexisting required
CENSURE c1004bd59b197d0db49c626ed24d6487547033adcabd99a0e19391e65872f33f.
Competing Design Review007 CENSURE b18853cb...54ce2a is redundant provenance only.

v7 prereg/audit SHAs8419502fff05cca1d38722fdcee0b6ef9f57256299225927c5901e240d852927 /
269aab5d0b0a3a0e99688dc70bdd84cb62db0235dac16665ffff5f0774a71047
remain PASS103/103 registration-only evidence. v7 is terminal with occupied CENSUREd
result paths and no route judgment. Heartbeat DELETED,TOML absent,quiet45s,Python0,
official hands0,L0. Next later boundary only fresh Route Review031 v8 reporting-only
preregistration plus independent preregistration audit with fresh paths and all
CENSUREs;no v8 result same boundary. No Design Review007/008,Revision007,witness,
pilot,asset,training,GPU,evaluator,Slumbot or checkpoint.

The 2026-07-22 13:33 update below is historical at its pre-v7-result census.

Current authoritative update (2026-07-22 13:33 EDT): Route Review031 v6 result/audit
SHAs9edd98e057913db7948b0f55e6e9851617741e3d1a30e72760847d0c5cb73326 /
654d122b9ea853fb8a6f52165a9663fca3eb598559c2a4a321bf33eb3f4a31a9 are
CENSUREd under SHA
dde8d81cb47ec89ada6845413d415d730faa6a9ab36163d8be56b38f4ce8babf
because their creation overlapped the root control refresh and violated the registered
single-writer contract. v6 is terminal without judgment;never repair,rerun,extend,
reclassify or infer from the reported PASS100/100.

The harmful heartbeat automation was deleted and its automation.toml is absent.
Authoritative Route Review031 v7 prereg/audit SHAs
8419502fff05cca1d38722fdcee0b6ef9f57256299225927c5901e240d852927 /
269aab5d0b0a3a0e99688dc70bdd84cb62db0235dac16665ffff5f0774a71047
PASS103/103 bind the exact v2 four-family registry,the valid v6 registration-only
predecessor and ten registration-time CENSUREs. v7 result/audit are absent;route
exhaustion false/unjudged;L0. No v7 judgment is authorized this boundary.

The already-running heartbeat turn then wrote Design Review007 prereg/audit SHAs
7a5c3ab4df61e726c3b7ee4bea2a25fec21dbf6153278628293050c7835ac850 /
45dbc07efadf544b583a34381019360af639b9f705c7c366996e033609fd5391
from the authority-NONE v6 result. Expanded CENSURE SHA
c1004bd59b197d0db49c626ed24d6487547033adcabd99a0e19391e65872f33f
makes both artifacts,snapshots and ledger event provenance only. Their result/audit
remain absent. Any later separately authorized v7 result must bind this eleventh
CENSURE and exclude all Design Review007 content. Next only later v7 reporting-only
result plus independent result audit. No Design Review007/Revision007,witness,pilot,
asset,training,GPU,evaluator,Slumbot,checkpoint or official hand.

The 2026-07-22 13:28 update below is historical and CENSUREd.

Current authoritative update (2026-07-22 13:28 EDT): fresh Phase FA Design Review007
preregistration/audit SHAs
`7a5c3ab4df61e726c3b7ee4bea2a25fec21dbf6153278628293050c7835ac850` /
`45dbc07efadf544b583a34381019360af639b9f705c7c366996e033609fd5391`
PASS120/120 establish
`PHASE_FA_DESIGN_REVIEW007_REGISTERED_PREREVIEW_AUDIT_PASS_RESULT_READY_ONLY`.
This is a new identity and new four-path namespace derived only from authoritative Route
Review031 v6,the exact V5.5 action/observation owner,the full-HUNL transition owner,
PCV019's interface-only planning evidence,and the narrow Revision003/Review004 failure
scopes. Stale Design Review006 CENSURE SHA b92ad047...b83ff2 is bound solely to exclude
all006/Revision006/Q006 witness,action algebra,pilot,quota,MC32,resource,selection,
method,behavior and strength content;none was reused.

The later static result must prove or reject exactly24 finite legal witnesses,one for
each200/100/50bb x preflop/flop/turn/river x actual actor tuple,starting from the
matching full-depth `deal_new_hand` and using only nonnull exact-V5.5 slot actions
through `apply`. It must resolve every slot collision from frozen owner rules and then
select exactly one preregistered candidate:base-context-only trajectory-native design;
a four-way total observable action-context partition only if a specific base-only risk
is proved;or constructive-route NONPASS returning to Route Review032. A PASS must also
freeze one exact48k-192k bounded8-CPU discovery pilot,20M base-only quota formula,
infoset-correct MC32>=32 with fresh hidden resampling,all-depth quality/resource gates,
and the path to a QA asset,one distilled checkpoint and mandatory quick5k. Global
census,unwitnessed quota,crossfill,projection,hidden leakage and postoutput adaptation
remain forbidden.

Latest complete external screen remains CAL-EXT-002 on frozen H11
iter35051/576,021,901:5,000 greedy-direct hands,-146.1726bb/100,95%CI
[-238.5979,-53.7473]. No checkpoint changed and no Slumbot screen is due. Result and
result-audit paths are absent;heartbeat PAUSED;an8-second seven-file watch observed
changes0 and CardPilot Python/Node0. Next is one later reporting-and-design-only
Design Review007 result plus one independent result audit,then stop. No witness/source
execution,census,pilot,implementation,qualification,asset,training,GPU,evaluator,
Slumbot,checkpoint or official hands;route_exhausted=false/unjudged by this review,L0.

The 2026-07-22 13:20 update below is historical at its post-route-review boundary.

Current authoritative update (2026-07-22 13:20 EDT): Route Review031 v6 result/audit
SHAs
`9edd98e057913db7948b0f55e6e9851617741e3d1a30e72760847d0c5cb73326` /
`654d122b9ea853fb8a6f52165a9663fca3eb598559c2a4a321bf33eb3f4a31a9`
PASS100/100 establish
`ROUTE_REVIEW031_V6_PASS_SELECT_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_DESIGN_ROUTE_NOT_EXHAUSTED`.
The result independently rehashed all33 exact v2 registry/protected inputs,bound the
original eight CENSUREs plus post-registration stale-result CENSURE SHA
`b92ad04754a86d86b3c7cc1f7eecfa79a6772b4ebb46e3f69b30dce63cb83ff2`,
and used no Q006,v4-result,Design Review006 or v5-attempt1 inference. Exactly four
families were judged and all remain open:critic is conditional on a future
post-distillation checkpoint;CFR/BC is the leading viable correction;league is untested
beyond H4;resolver remains prerequisite-limited. Route exhaustion is judged false.

The selected registered candidate is
`PHASE_FA_DESIGN_REVIEW006_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY`,
but every 006 artifact identity/path is permanently CENSUREd. Therefore the sole next
identity is fresh
`PHASE_FA_DESIGN_REVIEW007_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY`:
one later reporting-and-design-only preregistration plus one independent preregistration
audit,then stop. It must independently prove or reject24 finite depth/street/actual-
actor witnesses and freeze one bounded legal-trajectory pilot,base-only quota formula,
infoset-correct MC32>=32 and fresh all-depth resource exit;no 006 content may be reused.

Latest complete external screen remains CAL-EXT-002 on frozen H11
iter35051/576,021,901:5,000 greedy-direct hands,-146.1726bb/100,95%CI
[-238.5979,-53.7473]. No checkpoint changed,no Slumbot screen is due,official hands in
this review0,L0. Heartbeat remains PAUSED and an8-second seven-file stability check
observed changes0 and CardPilot Python/Node0. No Design Review007 registration this
boundary and no implementation,pilot,census,qualification,asset,training,GPU,evaluator,
Slumbot,checkpoint or official hands.

The 2026-07-22 13:17 update below is historical at its pre-v6-result census.

Current authoritative update (2026-07-22 13:17 EDT): Route Review031 v6 remains the
sole authority after stale Design Review006 result CENSURE. The stale continuation
wrote Design Review006 result/audit SHAs794a5399...59081f / 90020dbb...7ddcc,
reporting Revision007 selection,24 witnesses and PASS100/100 after its parent authority
was already NONE. CENSURE SHA
b92ad04754a86d86b3c7cc1f7eecfa79a6772b4ebb46e3f69b30dce63cb83ff2
makes every design,witness,pilot,resource,selection,route,method,behavior and strength
claim provenance only. Preserve without inference,repair,rerun,reclassification or
deletion. No pilot,asset,training or official hand occurred.

Route Review031 v6 prereg/audit SHAs6915d6a4...41e726 / 319d9e23...840bf8
remain PASS118/118 and authoritative. A later v6 result must bind all original eight
CENSUREs plus the post-registration b92ad047...b83ff2 CENSURE and exclude all Design
Review006 content from inference. v6 result/audit absent;heartbeat PAUSED;Python0;
route_exhausted=false/unjudged,L0. No Revision007,Design Review006 repair,Q006,census,
pilot,asset,training,GPU,evaluator,Slumbot or official hands.

The 2026-07-22 13:09 update below is historical at its registration-time census.

Current authoritative update (2026-07-22 13:09 EDT): Route Review031 v6 is the sole
authoritative registered boundary. A stale continuation created Design Review006
prereg/audit from the CENSUREd v4 result and overlapped Route Review031 v5 attempt1.
CENSURE SHA0247b90a5239c956d1dd17b6e3366b5b3727b4ada75d8e3805d90e8a32fcf713
gives Design Review006 SHAs48cc911b...dbd60b / bd9c6816...8e513 PASS259/259 and
v5 attempt SHAsce56202b...63ee69 / ecdcafc9...93e08 PASS115/115 provenance only.
Design Review006 relied on the authority-NONE v4 selection,and v5 audit falsely asserted
the two concurrent files were absent. Neither has result,design,route or execution
authority;never repair,rerun,reclassify or use them.

Authoritative Route Review031 v6 prereg/audit SHAs
6915d6a42eab85506f5366b3e1bbbcd70bcc2cf036ec2f23d8cf51aaf641e726 /
319d9e235cfc1840f7c74b64f38b0c8012badc4001427d56f900dcdf1b840bf8
PASS118/118 bind the exact v2 four-family registry,valid v4 registration-only
predecessor and all eight CENSUREs. Q006,v4 result,Design Review006 and v5 attempt1 are
excluded from inference. Fresh v6 result/audit paths are absent. Heartbeat PAUSED,
Python0,route_exhausted=false/unjudged,L0. Next is one later reporting-only v6 result
plus independent result audit;stop before automatic downstream registration. No
Design Review006,Q006,census,pilot,asset,training,GPU,evaluator,Slumbot or official hands.

The 2026-07-22 13:03 update below is historical and CENSUREd.

Current authoritative update (2026-07-22 13:03 EDT): Phase FA Design Review006
preregistration/audit SHAs
`48cc911b561bdf1f0bcf934dd3ab70702f3934473d9d68b7ce8cf70e82dbd60b` /
`bd9c6816a4cf51f05ad3dc2c560f20fdbb4b99494bd7830fbb161fdc6338e513`
PASS259/259 establish
`PHASE_FA_DESIGN_REVIEW006_REGISTERED_PREREVIEW_AUDIT_PASS_RESULT_READY_ONLY`.
The review is read-only static-source and frozen-evidence design work;source import,
compile,process,witness execution,state enumeration,census,pilot and random sampling are
all forbidden. It binds Route Review031 v4 PASS,the exact V5.5 owners,PCV019 planning-
only evidence and the Revision003/Review004 failure scopes. Both Q006 CENSUREs are bound
only to exclude Revision006 prereg/audit,runner,auditor,launcher,implementation audit
and self-test observation from witness,totality,pilot,resource or selection authority.

The later result must provide exactly24 finite static witnesses:one for every
200/100/50bb x preflop/flop/turn/river x actual actor tuple,starting only from
`deal_new_hand` and advancing only through exact nonnull V5.5 slot actions. It must then
select exactly one registered candidate. Rank1 uses only the24 witnessed base contexts
as preset quota domains and keeps line/raise/SPR/legal-signature/action-context as
empirical diagnostics. Rank2 is allowed only if a named base-only coverage risk exists
and the registered four-way observable action-context partition is algebraically total
and mutually exclusive. Rank3 freezes constructive-route infeasibility and returns to
four-family review. The result must also freeze one exact30k-300k bounded CPU discovery
pilot,20M quota formula,information-set-correct MC32>=32,all-depth fresh resource
projection and the path to one distilled checkpoint plus mandatory quick5k. No global
support map,unwitnessed quota,cross-key fill,hidden leakage,adaptive postoutput repair or
unbounded resource assumption is permitted.

Latest complete external screen remains CAL-EXT-002 on frozen H11 iter35051/576,021,901:
5,000 official greedy-direct hands,-146.1726bb/100,95%CI[-238.5979,-53.7473],L0.
No checkpoint changed and no Slumbot screen is due. Current-policy no-progress behavior
windows=0;nonbehavioral boundaries since v4 race recovery=2;single-writer and the one-
prereg-audit/one-result-audit ceiling remain active. All four non-V6 families remain
open;route_exhausted=false/unjudged by this review. Result and result-audit paths are
absent. Next is one later reporting-and-design-only Design Review006 result plus one
independent result audit;stop before new code,witness execution,pilot,qualification,
quota manifest,asset,training,GPU,evaluator,Slumbot,checkpoint or official hands.

The 2026-07-22 12:56 update below is historical.

Current authoritative update (2026-07-22 12:56 EDT): Route Review031 v4 result/audit
SHAs
`62fa20ba78f5449ee63cd90b89f60f6b135aebfc31dcf2811f7283100b273667` /
`3211b78ac0067ca6d2173cc8c416997af391c74a74b1466005495c21d5484bbd`
PASS175/175 establish
`ROUTE_REVIEW031_V4_PASS_SELECT_PHASE_FA_DESIGN_REVIEW006_ROUTE_NOT_EXHAUSTED`.
The result binds v4 prereg/audit PASS81/81,the concurrency/clock CENSUREs and the
corrected v2 full registry;all33 registry evidence hashes independently match. Exactly
four families were judged. Critic magnitude remains open but conditional on a future
valid distilled checkpoint and may never replay EXP-W1/H1/H6/H18. Opponent league
remains open but H4 supplies no current causal candidate. Resolver remains open with
all six H5 prerequisites unresolved. CFR/BC is highest information gain because PCV019
proves the exact-V5.5 bounded interface while Path1/H3,Q001,Revision003 and Review004
close only their exact projection,identity,Cartesian-quota or global-census designs.

Selected next is
`PHASE_FA_DESIGN_REVIEW006_TRAJECTORY_NATIVE_CONSTRUCTIVE_WITNESS_AND_BOUNDED_DISCOVERY_FEASIBILITY`.
It must prospectively prove finite exact legal-action witnesses across200/100/50bb,
all streets and actual actors;use only witnessed reached semantic keys;resample hidden
information per MC rollout;preserve exact nine-slot MC32>=32;bound discovery and the
full asset projection;and name the path through one distilled checkpoint and mandatory
quick5k. Global census,unwitnessed Cartesian quota,cross-key fill,CFR/legacy projection
and repeated interface smoke are forbidden. The censured concurrent Revision006/Q006
artifacts and `line_bucket_unclassified` observation have no selection or design
authority. Expanded Q006 execution CENSURE SHA
`27270196e3b51d8cd258ba01a8948324daf7f101316894d75bf7b40ef79ada2d`
and redundant reconciliation CENSURE SHA
`a1f340c58549439058ea297e668b681f5cacdb333b82e66a4555b91e65e7aa96`
are provenance only;preserve all bytes and never run or reuse them.

Latest complete external screen remains CAL-EXT-002 on frozen H11 iter35051/576,021,901:
5,000 official greedy-direct hands,-146.1726bb/100,95%CI[-238.5979,-53.7473],L0.
No checkpoint changed and no Slumbot screen is due. Current-policy no-progress behavior
windows=0;nonbehavioral boundaries since v4 race recovery=1;the single-writer rule and
one-prereg-audit/one-result-audit ceiling are active workflow simplifications. All four
non-V6 families remain open;route_exhausted=false. Next is one separately registered
Design Review006 reporting-and-design-only preregistration plus independent audit only;
stop before its result,code,witness execution,pilot,asset,training,GPU,evaluator,
Slumbot,checkpoint or official hands.

The 2026-07-22 12:53 update below is historical.

Current authoritative update (2026-07-22 12:58 EDT): Route Review031 v4 result/audit
are CENSUREd with no judgment. After heartbeat PAUSE,the already-running continuation
wrote v4 result/audit SHAs 62fa20ba...273667 / 3211b78a...84bbd,reporting Design
Review006 selection and PASS175/175. CENSURE SHA
24b36a726c9c6fa97e66225e81c3989bfb36a248ff08b26194630039f96ad852
makes both provenance only. The result was created after but omitted expanded Q006
CENSURE SHA27270196...ada2d,and result/audit creation overlapped the root control
refresh,contradicting the audit's exclusive single-writer premise and the PAUSE contract.
Preserve but never repair,rerun,reclassify or use the reported selection. Route
Review031 v4 prereg/audit dce25be4...02cb6 / 03d71a81...e205a remain PASS81/81,
but v4 is terminal with occupied CENSUREd result paths and no route judgment. Route
exhaustion=false/unjudged;heartbeat PAUSED;L0. Next is only a later separately
registered Route Review031 v5 reporting-only preregistration plus independent
preregistration audit using fresh paths and every CENSURE chain;stop before its result.
No Design Review006,Q006,asset,training,GPU,evaluator,Slumbot or official hands.

The 2026-07-22 12:53 update below is historical.

Current authoritative update (2026-07-22 12:53 EDT): Route Review031 v4 remains the
sole authoritative boundary after expanded Q006 concurrent-execution CENSURE. After
the time-local runner-only census,the already-running heartbeat also wrote Q006
auditor/launcher/implementation-audit artifacts and ran one zero-file `--self-test`.
Expanded CENSURE SHA
27270196e3b51d8cd258ba01a8948324daf7f101316894d75bf7b40ef79ada2d
binds runner/auditor/launcher/implementation-audit SHAs b9ff1a88...d70d26d /
3da665a3...713b38 / 423a8326...2b476 / 3dcd3cbd...bfabb. The reported
PASS60/60 / FAIL_CLOSED and `line_bucket_unclassified` observation have no design,
qualification,route or strength authority because parent Revision006 was already
CENSUREd. Contract probes,qualification attempts,support/MC32 rows,output/asset roots,
training,GPU,Slumbot and official hands remain0/absent. Preserve all bytes;never repair,
rerun,reclassify or use them. Heartbeat is PAUSED;the 30-second drain census observed
zero changes and Python processes0. Authoritative Route Review031 v4 prereg/audit SHAs
dce25be46bf5f0a9d21a85bba8c1a4bae104fe47bc7a9583e3bfa90753002cb6 /
03d71a81f8f55053426b0e24168b3c1507fd867303dc8d7c95e671ad0dbe205a
remain PASS81/81;both v4 result paths are absent and route exhaustion is false/unjudged.
Only a later separately authorized reporting-only v4 result plus independent audit may
follow. No Q006,asset,training,GPU,evaluator,Slumbot or official hands. L0.

The 2026-07-22 12:37 update below is a time-local historical snapshot.

Current authoritative update (2026-07-22 12:37 EDT): concurrent heartbeat writes are
terminal CENSUREd and Route Review031 v4 is the sole authoritative registered boundary.
Concurrency/clock CENSURE SHAs
14749e36485285e27acdc217662597d82860b6ab2d18cf2026543636c36d6103 /
0c72ca6c46d207f24a896058daf7bb4ed6b5ce2d38ed451f9a485b2a0a228766
preserve v1 prereg/audit/result/result-audit,v2,v2-audit-attempt1 and v3/v3-audit.
The v1 result/audit SHAs b40a5b7f...e21d8 / 2437302b...8fb3 have no
judgment authority because v1 omitted EXP-W1 and PCV015/H3-v3 from the required full
four-family registry and the result was written after v1 CENSURE/v2 registration.
Revision006 prereg/audit SHAs c7f3645b...efd42 / 976c2721...91b0 PASS267/267
were concurrently derived from that unauthorized result and also used future declared
timestamps;CENSURE SHAa5f256ba0f4397f4ffddb7813ec7687990bfc480065c84f0870ce501a8786afa
gives them provenance only and no Q006 authority.
The same already-running continuation later wrote only Q006 runner SHA
b9ff1a880abffa8d107b9ee7149183e36183c040375f675ee0d40addbd70d26d.
Runner CENSURE SHA18c7076447fd006ba2a71ab047c04395a0314bd0332e9d02d32fb5aa4941784b
binds launcher/auditor/implementation-audit/output roots absent,probes/qualification/
support discovery0 and no Python process. Preserve but never compile,self-test,launch,
audit,repair or use it.

Authoritative Route Review031 v4 prereg/audit SHAs
dce25be46bf5f0a9d21a85bba8c1a4bae104fe47bc7a9583e3bfa90753002cb6 /
03d71a81f8f55053426b0e24168b3c1507fd867303dc8d7c95e671ad0dbe205a
PASS81/81 bind the corrected four-family registry,fresh exclusive v4 result paths and
nonfuture timestamps. No v4 result/audit exists;route_exhausted=false/unjudged. Next
is one later reporting-only v4 result plus independent audit. No Revision006 design,
Q006,process,census,pilot,asset,training,GPU,evaluator,Slumbot,checkpoint,H19/later
behavior or official hands. L0.

The 2026-07-22 12:43 update below is historical and CENSUREd.

Current authoritative update (2026-07-22 12:50 EDT): Revision006 Q006 implementation
is terminal
`PHASE_FA_REVISION006_Q006_IMPLEMENTATION_FAIL_CLOSED_INITIAL_PREFLOP_INFOSET_UNCLASSIFIED_BY_FROZEN_LINE_BUCKETS_NO_QUALIFICATION`.
Runner/auditor/launcher SHAs
`b9ff1a880abffa8d107b9ee7149183e36183c040375f675ee0d40addbd70d26d` /
`3da665a34968a6fd37bd705da249959b3532809a6e808b9ae260a3ea6f713b38` /
`423a832663d9d3bef038825e1da398fac629ae6d0d908d5fa750e2d557a2b476`;
independent implementation-audit SHA
`3dcd3cbd853df045e015f3426b4cacdc222758493cd15f098ec1d147160bfabb`
has audit-integrity PASS60/60 and implementation overall FAIL_CLOSED. Python AST and
PowerShell parse passed,but the zero-file self-test exited1 at `line_bucket_unclassified`.
An independent exact-owner reproduction passed3/3:the first acting state at200/100/50bb
is SB preflop facing the posted BB,with to_call0.5,engine raise_count0,actions[0,1,7,8]
and no match among the eight frozen line predicates. Revision006 simultaneously requires
accepting every first-seen reached nonterminal infoset,so this mandatory state cannot be
silently skipped or forced into `FACING_FIRST_BET` without changing the prospective
dataset definition. This is a structural scientific design failure,not an eligible
pre-output control-plane correction. Preserve the three code files and audit as terminal
evidence;do not repair,reregister the same schema,run ContractProbe,or launch Q006.
Qualification attempts0,support/MC32 rows0,output/asset roots absent,checkpoint unchanged,
Slumbot hands0.

Latest complete external screen remains CAL-EXT-002 on frozen H11 iter35051/576,021,901:
5,000 official greedy-direct hands,-146.1726bb/100,95%CI[-238.5979,-53.7473],L0.
No external screen is due. Ranked teacher hypothesis remains open,but its immediate
blocker is now a prospectively complete mutually-exclusive reachable-state line schema
that handles blind-facing preflop without restoring Cartesian quotas or target search.
Current-policy no-progress behavior windows=0;post-simplification nonbehavioral/
preoutput boundaries=2;all four non-V6 families remain scientifically open and
route_exhausted=false. Next is one separately registered compact scientific Route
Review032 with workflow simplification and independent audit only;it must re-rank the
four families and may select a fresh prospective design,but must stop before new code,
probe,qualification,asset,training,GPU,evaluator,Slumbot or official hands.

The 2026-07-22 12:43 update below is historical.

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
