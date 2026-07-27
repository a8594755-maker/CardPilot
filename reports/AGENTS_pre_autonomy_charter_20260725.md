# CardPilot Agent Workflow

## Current Objective

Reproduce and extend AlphaHoldem for 200bb heads-up no-limit Hold'em with an
end-to-end RL agent. The reference paper is Zhao et al., "AlphaHoldem:
High-Performance Artificial Intelligence for Heads-Up No-Limit Poker via End-to-End
Reinforcement Learning," AAAI 2022.

Primary target: beat Slumbot at 200bb. A valid L5 win claim requires one exact frozen
V5-lineage policy, at least 100,000 complete official greedy-direct Slumbot hands,
bb/100 greater than 0, a 95% confidence-interval lower bound greater than 0, and a
complete independently audited hand-level evidence bundle. The stretch target is near
the paper result, approximately +11.1 bb/100 versus Slumbot.

Do not claim V4/L5/L6 strength from training health, self-play reward, internal probes,
2k diagnostics, quick5k, or an incomplete external bundle.

The only completion states are:

1. The L5 claim bar above is met.
2. A frozen escalation proves that critic/target design, exact-V5.5 CFR/BC teacher
   warm-start, opponent league, and play-time resolver are each scientifically
   exhausted and no viable non-V6 correction remains.

## Operating Precedence And Document Hygiene

Use this order:

1. Current user and platform instructions.
2. The objective and research constitution in this file.
3. The single current authoritative state in this file.
4. Exact identity-bound artifacts and append-only evidence.
5. The immutable history snapshot and experiment ledger, which are evidence only.

Never replay, repair, mutate, or infer authority from a frozen historical attempt.
Historical `Next only`, `stop`, PID, nonce, checkpoint, cadence, or launch clauses do
not govern after a newer user instruction and this current state supersede them.

Keep this file prospective and compact. It contains policy plus exactly one current
state. Preserve chronology in append-only reports and snapshots. Before replacing this
file materially, preserve its predecessor as a read-only snapshot and record its
pre-migration SHA256 in the new history pointer.

## Research Constitution

Optimize for externally demonstrated poker strength and information gain, not audit
PASS counts, self-play volume, documentation volume, identities, or closed boundaries.
Audits and control-plane checks are enabling controls, not scientific progress.

- Maintain ranked falsifiable hypotheses across critic/target design, exact-V5.5
  CFR/BC teacher warm-start, opponent league, and play-time resolver.
- Prefer the smallest coherent causal intervention that can distinguish the leading
  hypotheses. One behavior-affecting intervention may contain inseparable changes
  required by that hypothesis; it need not be one scalar.
- Re-rank before registration when frozen evidence warrants it. Never redesign a
  registered behavior window after scientific output begins.
- Slumbot is the primary directional signal and sole formal strength authority.
  Internal probes, teacher holdouts, losses, and training metrics localize mechanisms
  but never substitute for external evidence.
- Spend effort in proportion to information gained. Use the smallest deterministic
  contract test that answers a control-plane question.
- Preserve immutable terminal scientific evidence and complete raw external evidence.

Within an active compatible goal, the agent may autonomously progress through all
registered boundaries in the four non-V6 families. Escalation is required only for V6
architecture/observation redesign, changing the objective, claim bar, or official
greedy-direct policy, spending money, secrets, destructive action, or scientific
exhaustion of all four routes.

## Accelerated Execution Policy

A registered boundary is a durable evidence checkpoint, not a mandatory end of an
agent turn. When a preceding gate passes, continue in the same authorized execution
program through implementation, proportionate independent audit, bounded execution,
exact judgment, and required external evaluation.

Do not stop merely because a preregistration, implementation, audit, qualification,
snapshot, or ledger append completed. Stop only when:

1. A behavior window or external evaluation reaches a result that requires scientific
   re-ranking.
2. A registered abort, safety, or immutable evidence condition triggers.
3. Progress requires an escalation listed in the Research Constitution or user input.
4. An external dependency is unavailable and no useful in-scope work remains.
5. The objective reaches one of its two completion states.

Apply full preregistration and independent-audit governance to behavior/model changes,
training-data generation, checkpoint creation, and official evaluation. Batch
read-only, reporting-only, launcher-only, path-only, and reversible control-plane work
into the smallest practical transaction. Verify such work with deterministic contract
tests unless an existing immutable registration explicitly requires more.

Independent audit means independently implemented verification; it does not require a
separate agent turn. Use stable reusable runners and auditors with content-addressed
configuration when compatible with frozen evidence. Do not duplicate source, require
whole-source AST equality, create another route review, or create another identity
chain when targeted contracts provide the same assurance, except where an already
active immutable registration explicitly requires those controls.

One meaningful scientific/external boundary should normally produce one compact
manifest, one independent audit, one judgment, one ledger append, and one current-state
refresh. Do not create a documentation boundary whose only outcome is another
documentation boundary.

## Adaptive Research Loop

For every behavior/model-changing program:

1. Establish the exact current checkpoint, latest complete external evidence,
   structural leaks, route state, and blocker.
2. Separate realized-loss localization, association, counterfactual evidence,
   same-start method effects, and formal external strength.
3. Rank falsifiable hypotheses and select one coherent intervention with an explicit
   reason it should improve external play.
4. Preregister source identity, budget, outcomes, external trigger, abort criteria,
   rollback, and interpretation rules.
5. Implement and validate proportionately to risk; independently audit before
   behavior, generated training data, checkpoint creation, or official hands.
6. Run the bounded window once and judge it exactly as registered.
7. Run the required external screen before another behavior window.
8. Retain, roll back, fundamentally revise, switch family, or freeze scientific
   exhaustion; then refresh the single current state.

No self-play continuation is justified only because training is healthy. State what
new information the additional hands provide and where external evaluation occurs.

## External Slumbot Evaluation Cadence

- Run one complete greedy-direct quick5k after every completed behavior-affecting
  training window and every new BC/distillation checkpoint eligible to seed RL, before
  another behavior window.
- During a longer unchanged training window, do not add more than 20M self-play hands
  between frozen quick5k checkpoints unless preregistered otherwise or an external
  outage is documented.
- Do not run Slumbot after reporting-only, audit-only, interface-only, or teacher-asset
  work when no deployable policy behavior changed.
- Quick5k is directional elimination evidence only. It cannot establish V4/L5/L6.
- Promote to 20k only through a preregistered quick5k plus mechanism/quality gate.
  Launch formal100k only when frozen 20k evidence makes L5 statistically plausible
  under a preregistered rule.
- Retain hand JSONL, decision dump JSONL, CI, promotion decision, loss report, artifact
  audit, and hand review for every screen. An incomplete bundle is no result.

The absence of a new deployable policy is a valid reason not to run Slumbot. The fact
that quick5k cannot prove strength is never a reason to omit a required directional
screen after behavior changes.

## Failure Taxonomy And Recovery

1. **Scientific failure.** Freeze the result, never rerun that exact scientific
   window, and re-rank the remaining hypotheses. The re-ranking and next compatible
   registration may occur in the same agent turn.
2. **Pre-output control-plane failure.** No behavior, scientific rows, generated
   training data, checkpoint, or official hands were produced. Preserve the failed
   implementation identity. One fresh corrected implementation attempt may proceed
   immediately without route review when scientific design, checkpoint, budget,
   outcomes, and evaluation gates are unchanged. It is a new attempt, not mutation of
   the failed identity. A recurrence requires immediate workflow simplification, which
   may also be completed in the same turn.
3. **Inconclusive evidence.** Do not force PASS or FAIL or extend samples post hoc.
   Re-rank by expected information gain.
4. **Evidence-bundle failure.** Preserve the incomplete run. Rebuild derived reporting
   only from complete immutable raw evidence. Missing or corrupt hand/decision evidence
   requires a fresh registered evaluation.

A structurally impossible design is a design failure, not a control-plane typo. Freeze
it and select the smallest scientifically valid redesign. Do not use failure taxonomy
to turn path, import, quoting, output-counter, file-size, or launcher defects into
scientific route exhaustion.

## Meta-Review And Progress Guards

- After two scientifically valid behavior windows fail their preregistered external
  directional criterion, stop local tuning and switch or fundamentally revise the
  hypothesis family.
- On the first repeated control-plane root cause, simplify immediately. At no point may
  three consecutive control-plane/nonbehavioral boundaries occur without either
  clearing the named blocker or replacing the workflow.
- A nonbehavioral step must clear a named scientific blocker and have an exit criterion.
  Audit completion alone is not an exit criterion.
- Refresh the current state after a meaningful scientific or external boundary, not
  after every file or checker.
- Route exhaustion is scientific, never administrative. It requires frozen evidence
  that no viable correction remains in all four non-V6 families.

## Current Authoritative State

Current authoritative update (2026-07-24): VR004 identity
`94e75a5e4df38d2ff7270e0a3ef5a6edfddd4db4f0d1e70bd0ff8bb2c749675b`
is terminal `VR004_PREIMPLEMENTATION_STRUCTURAL_NONPASS_WORKFLOW_REDESIGN_REQUIRED`.
Preregistration/failure SHAs are
`2923e5fb20cd0d94331ff24b093864263ea6293f7c1779e84fe6fd1134bc04ff` /
`61ade49bc152b1c89e6d475b71df52a12fdc595397d94214a53de7fa1110f873`.
Independent red-team proved the behavior configuration underfrozen;the fresh
per-hand selector changed the measured per-update opponent/batching topology and
conflicted with mirrored self-play;the FIFO hand-packet protocol lacked a global
reconstructable order;and the supervisor/raw-evidence graph was incomplete. The
preimplementation audit was stopped before script/report materialization.
Implementation,model,updates,training,checkpoint,Slumbot and official hands0.
Preserve VR004;never implement,repair,rerun or reclassify it. This is not Qboost
scientific evidence.

The repeated thin-overlay preregistration workflow is now the named root failure.
Before another behavior identity,the research goal/workflow must be simplified to
one content-addressed executable experiment package containing the full training
config,one opponent/deal/inference topology,one hand-packet ordering protocol,one
monotonic supervisor,all raw-evidence schemas and one independently implemented
verifier. Parallel design,implementation,resource modeling and red-team work should
occur before registration inside disposable non-scientific paths. Register exactly
once only after the whole package passes deterministic no-model contracts and a
frozen-rate feasibility check. Do not create another overlay identity merely to
repair a path,prose contract,checker or missing schema.

VR002C1 remains invalid and its provisional state forbidden. Qboost science remains
open,as do simplified normal-form teacher,adaptive league and public-belief resolver.
Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k remains CT003 -145.462bb/100,CI95[-227.9171,-63.0069]. Eligible checkpoints0;
formal-claim hands0;strength L0;route exhaustion false;goal ACTIVE. Ledger SHA
`8ebcffc7c0a3cf9a1a8a40167bbc42cd3a702b3e4a8c51516bd59f49e3579694`.
Next requires a user-approved replacement goal/workflow because it materially
changes how scientific identities are created and governed;no further registration,
implementation or execution under the current overlay workflow.

Historical VR003C1 update (superseded by the state above): VR003C1 identity
`ad4f8d47e084a2e47c8f64efae465fd816d5af5d7dc4448cbe8392a9498b6a3a`
is terminal `VR003C1_PREIMPLEMENTATION_STRUCTURAL_NONPASS_SIMPLIFY_TO_VR004`.
Preregistration/failure SHAs are
`c2b3eb558db0e8855fafc15645103e6eae3c43a9ac9e09d62853b4a0858f5ffd` /
`a1ee63277ff4c59e82e9282ddc8c1a647b2c53807101522224091c8ed95d74aa`.
Independent review proved four contradictions:the parent/C1 semantic projection was
undefined;fresh assignment seed conflicted with the hardcoded frozen selector;the
launcher-owned monotonic watchdog conflicted with frozen blocking PowerShell;and
unbounded pipe draining gave no proof that first crossing stayed within1.92M.
An audit draft SHA
`2e3ff632e3713ce919a107b2476f23c5c403c18ab904d29f034d5a390a474416`
materialized before the stop but was never executed;report absent. Implementation,
model,training,checkpoint,Slumbot and official hands0. Preserve VR003/VR003C1 and
the draft;never audit,implement,repair,rerun or reclassify them.

Workflow simplification selects new-design VR004,not another correction. It retains
the Qboost causal intervention but uses exactly116 completed PPO updates with exactly
16,384 generation-pure admitted hands per update,for exactly1,900,544 scientific
hands;surplus pipe hands are retained and counted but cannot enter the update. It
uses a fresh self-contained deterministic assignment selector,not the frozen LG003
runtime selector,and a fresh Python supervisor owning monotonic21,600s timeout,
stdout,stderr and child exit. Its contract must be explicit and targeted;whole-source
or prose semantic equivalence is forbidden. Frozen admitted-pure HPS plus overhead
projects20,657.972511s,leaving942.027489s. Every valid audited116-update endpoint
must run greedy-direct4x1,250 quick5k.

VR002C1 remains an invalid provisional endpoint and forbidden input. The simplified
normal-form teacher,adaptive league and public-belief resolver remain open.
Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k remains CT003 -145.462bb/100,CI95[-227.9171,-63.0069]. All four families
remain open;eligible checkpoints0;formal-claim hands0;strength L0;route exhaustion
false;goal ACTIVE. Ledger SHA
`dc4668cef00cfd8e7a986683c4dc29c9eb9aadae3453c593bf00317a0208212b`.
Next is one fresh VR004 preregistration plus independent preimplementation audit;no
implementation or execution before audit PASS.

Historical VR003 update (superseded by the state above): VR003 identity
`15c162514c345eec0ddeda67d97d3931e13ad65fcad1c3fc20db3ac1c2f750c5`
is terminal `VR003_PREIMPLEMENTATION_INPUT_PATH_SHA_MAPPING_FAILURE`.
Preregistration/failure SHAs are
`72bc18693aad9bd0c154cbdd5741240bf2043bae5dad53055727ba40dcab9a27` /
`2490ebfedca071e71e24744f4e93d922fadf40f37a2c15a7f2ce58294bfc4e6a`.
Local rehash before audit found that the body mislabeled the VR002 preregistration
path with the VR002C1 SHA and supplied a nonexistent SHA for the actual C1 path.
Correct observed path-to-SHA mappings are VR002
`029411e18760455197471a12f0c00c07d08e6d3123e3d8d62e4b51bc6b7b6fcd`
and VR002C1
`a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e`.
This is a pre-output identity defect;audits,implementation,model,training,checkpoint
and hands0. Preserve VR003;never repair,implement,rerun or reclassify it. Its sole
fresh C1 may change only identity/token,authority/prospective paths and those two
mappings;all science,resource,seeds,endpoint,external and judgment contracts remain
exact.

The post-F8R4 simplified meta-review remains PASS and selects
`VR003_RESOURCE_SIZED_FAITHFUL_QBOOST`:result SHA
`4cbdc91ce0cb0d123d8bd1d78e2891643b15bf15887a95511fc10005e484d3e5`.
The corrected fresh design starts from exact H11,never VR002C1 provisional state,
and targets first crossing1,900,000--1,920,000 generation-pure hands. Frozen
resource projection remains20,652.764138s under21,600s. Any valid audited endpoint
must run greedy-direct4x1,250 quick5k.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k remains CT003 -145.462bb/100,CI95[-227.9171,-63.0069]. All four families
remain open;eligible checkpoints0;formal-claim hands0;strength L0;route exhaustion
false;goal ACTIVE. Ledger SHA
`160ae7e5f9162f351efbaa867bb52f632d7bb6d2b347d9a72a321b57a7fcd417`.
Next is one VR003C1 mapping-correction preregistration plus independent audit;no
implementation or execution before audit PASS.

Historical post-F8R4 meta-review update (superseded by the state above): the review
identity/result SHAs are
`5fa7d0f3701e7ea962fb894e536d06969de06d6860e2aa235e8f13e5f99d1305` /
`4cbdc91ce0cb0d123d8bd1d78e2891643b15bf15887a95511fc10005e484d3e5`;
deterministic hash/arithmetic checks PASS and select rank1
`VR003_RESOURCE_SIZED_FAITHFUL_QBOOST`. No F8R5 was registered. Two independent
pre-registration red-teams found unresolved full-joint teacher contradictions in
RNG open-interval mapping,E1 isolation,census overflow,solver-tree/root/chance work,
phase paths and evidence schemas. After F8R2/F8R3/F8R4 consumed three consecutive
pre-science structural/control boundaries,the simplification guard forbids another
full-joint depth-two registration.

VR003 is a new critic/target behavior design,not a VR002C1 correction,resume or
replay. It must start from exact frozen H11 and use fresh identity,source,output and
seeds;the frozen VR002C1 provisional checkpoint,Q state,optimizer and metrics are
permanently ineligible inputs. The coherent intervention remains training-only
centralized Q9 Expected-SARSA(lambda=.95) Qboost under the frozen official actor,
opponent/deal contract and greedy-direct policy. The endpoint unit changes from
total complete hands to generation-pure admitted complete hands:minimum1,900,000,
maximum1,920,000,first crossing only. Frozen conservative admitted-pure HPS
104.44721299953976 plus2,461.7569733s overhead projects20,652.764138s under the
21,600s cap,leaving947.235862s headroom. Any valid audited endpoint must run one
complete greedy-direct4x1,250 quick5k regardless of mechanism PASS/FAIL.

VR002C1 remains terminal invalid endpoint with cause UNPROVEN;its3,064,100 complete/
2,649,478 generation-pure partial window and150/161 variance-ratio-below1 rows are
mechanism-localization evidence only,never checkpoint or strength authority.
F8R2/F8R3/F8R4 remain frozen design failures. A later simplified source-hole
normal-form CFR+ teacher remains open;adaptive league and public-belief resolver
remain open but deprioritized.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k and last screened checkpoint remain CT003 -145.462bb/100,
CI95[-227.9171,-63.0069]. All four families remain open;eligible checkpoints0;
formal-claim hands0;strength L0;route exhaustion false;goal ACTIVE. LRFT ledger SHA
`5b03d023bd1c257972a68297517696620aabe16462fbf9c5a3bb402eb4cd6bb0`.
Next is one fresh VR003 candidate-specific preregistration plus independent
preimplementation audit. No implementation,training,checkpoint or Slumbot before
that audit PASS.

Historical F8R4 update (superseded by the state above): LRFT-F8R4 identity
`165822f101c1da7589cb3a605d16abbc1c2da669f170591b0f9d2ee3c5cedbad`
is terminal
`LRFT_F8R4_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_MISSING_E0_RAW_AUTHORITY`.
Preregistration/failure SHAs are
`b72590708e3f13bf41044fcade01ff13b57a61fa5a9c29adcd267053cef6702c` /
`9cc0348d223374109bb6cca99fbf1098eeb1cf8fd614039d960c810b24197422`.
Its E1-open contract requires hashes of candidate,A/B endpoints and raw E0
evidence,but the prospective path set registered no create-new E0 raw artifact or
explicit solver raw/A/B endpoint artifacts. Adding them after registration changes
scientific output identity;omitting them makes E0 judgment,E1 binding and independent
result audit unreconstructable.

The first independent F8R4 prereg auditor also terminated pre-output while serializing
the degenerate CI fixture `df=+inf` under `allow_nan=False`;source/partial SHAs are
`33163bce36b54903f64f7c75f744db22964da9a5a031479d4e5c2b53221ef8ca` /
`8dd6a3ed72a2e834d9de8f96abef71a283d2fcfac3583eea13e41d159a817969`.
Its contemplated serialization-only C1 was stopped before materialization when the
structural path defect was found. No F8R4 implementation,model,network,resource or
science occurred. Preserve F8R4 and the partial audit;never correct,audit,implement,
repair,rerun or reclassify them.

Before F8R5 registration,two read-only design reviews must close the complete
prospective output/schema/phase-binding graph,E1 process isolation,RNG domain/key
tuples,root-average stream semantics,work-cap interpretation,passive closure and
resource accounting. F8R5 may retain the fixed-eight hypothesis only after those
reviews find a self-contained satisfiable contract.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k and last screened checkpoint remain CT003 -145.462bb/100,
CI95[-227.9171,-63.0069]. All four families remain open;eligible checkpoints0;
formal-claim hands0;strength L0;route exhaustion false;goal ACTIVE. LRFT ledger SHA
`f67e1ed63cfc0797a9f73e011dfe352ab63bfa80bbbf6ad5c067cc1a41840e46`.
Next only is finish the two F8R5 pre-registration design reviews and exact reranking;
no registration,implementation,model,resource or science until they finish.

Historical F8R3 update (superseded by the state above): LRFT-F8R3 identity
`d47c166ce97cd20019b0ff31df8045a6334b0430761932fa41a34cb4fef1368c`
is terminal
`LRFT_F8R3_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_RESOURCE_PADDING_DOUBLE_COUNT`.
Preregistration/failure SHAs are
`66cfde7ae673d5caff748203f3d8aa88aa5bf011d362c5191d9b64adad709e46` /
`b6313544da478498eab20520b296d537f34a0d9bf3932dccc332d6e3ec018529`.
Its registered5,109.8081s resource projection used6,844,416 as the complete padded
scheduler-operation envelope,but its JSON mislabeled that value as base transitions
and added288,360 passive actions a second time. The resulting7,132,776 envelope did
not match the projection. Exact complete-science scheduler cap is6,264,425,so one
future fresh identity must use6,844,416 as the total action+passive+chance resource
envelope,leaving579,991 operations of margin and adding nothing again. The pending
independent audit was interrupted before any file. No F8R3 audit,implementation,
model,network,resource,census,root,belief,solver,E0,E1,teacher,checkpoint,Slumbot
or official hand occurred. Preserve F8R3;never audit,implement,repair or reclassify.

Same-turn reranking selects fresh F8R4 with that sole accounting correction. Its
science remains eight fixed roots,two replicas x2,048 iterations,E0 2,048 and sealed
E1 4,096 tapes/root,H11-P256 at most8 post-root actions then passive exact closure,
and fixed-root paired analytic one-sided inference. Science exact is66,688 network
calls,17,072,128 rows,720,896 outcomes,5,795,840 base actions,up to288,360 passive
actions and180,225 chance/runout operations. Resource admission uses one total
6,844,416 scheduler-operation padding envelope and70,784 network calls.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k and last screened checkpoint remain CT003 -145.462bb/100,
CI95[-227.9171,-63.0069]. All four families remain open;eligible checkpoints0;
formal-claim hands0;strength L0;route exhaustion false;goal ACTIVE. LRFT ledger SHA
`ee336571261389cc25f5dcb10c3ef62c4f13bb1dfaf50c8cfc7e636e0eae2f6f`.
Next is one fresh F8R4 preregistration plus independent preimplementation audit.
No implementation,model,resource benchmark or science before audit PASS.

Historical F8R2 update (superseded by the state above): LRFT-F8R2 identity
`a424689522962d2a61eab3c530f1fc5daf7fd701f64f22908adb92d3e2978cfc`
is terminal
`LRFT_F8R2_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_PASSIVE_WORK_OMISSION`.
Preregistration/failure-report SHAs are
`e2f8a92c82d238edd7a47e9471a12d943d4940ff0bc95fc2ddbe735532faa563` /
`cebde5e41eac63b10c1c7f60614f1f58f6bd0348639ef7fb56208c4af61ee996`.
Independent formula review proved that the registered5,795,840 exact-cent action
transition cap omitted the passive exact terminal-closure work required by its own
estimand. At720,896 outcomes and fallback<=5%,a PASS may require288,352 additional
passive actions;fail-closed accounting requires total action-transition cap
6,084,200 plus chance/runout-operation cap180,225. Removing the passive tail would
change the intervention and estimand. No F8R2 implementation,model,network,resource,
census,root,belief,solver,E0,E1,teacher,checkpoint,Slumbot or official hand occurred.
Preserve F8R2 read-only;never implement,repair,rerun or reclassify it.

Same-turn scientific reranking selects one fresh F8R3 identity retaining the
fixed-eight hybrid-continuation hypothesis while explicitly bounding passive action
and chance work. Its exact science envelope is66,688 network calls,17,072,128 rows,
720,896 outcomes and base5,795,840 action transitions;its terminal envelope adds
at most288,360 passive action transitions and180,225 chance/runout operations.
Resource admission must use the larger70,784-call padding envelope and the frozen
F8R1C1 minimum rates,whose projection is approximately5,110s against21,600s.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k and last screened checkpoint remain CT003 -145.462bb/100,
CI95[-227.9171,-63.0069]. Last behavior change CT003;consecutive valid external
nonimprovement windows1. Rank1 exact-V5.5 teacher;rank2 critic/Qboost open but
resource-deprioritized;rank3 adaptive league;rank4 resolver. All four families
remain open;eligible checkpoints0;formal-claim hands0;strength L0;route exhaustion
false;goal ACTIVE. LRFT ledger SHA
`2db826634a9fb4fdf053c66204007e3b612b348e266c8044202cacdfdbc674df`.
Next is one fresh F8R3 preregistration plus independent preimplementation audit.
No implementation,model,resource benchmark,census,root,belief,solver,evaluation
tape,teacher row,checkpoint,Slumbot or official hand before that audit PASS.

Historical F8R1C1 update (superseded by the state above): LRFT-F8R1C1 is terminal
`LRFT_F8R1C1_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS`. Its sole frozen
resource-result SHA is
`6783a63c3026303a4144b8b3a4b08cfa20ed5d91eb194d11f05348368fe3d367`;
independent resource-auditor/result SHAs are
`3d667fdcf532ba5316b955a4144b3955d7b96f43b3cae94ab4288d228f2bde2e` /
`1f86e91f3b0341cdb99848b72184f573d5161bb04866c8146b15d5f894d6a0ae`
with PASS7/7. The exact projected wall was113,021.17911923451s against the
registered21,600s limit;this was the sole failed gate. Stage projections were
bootstrap54,146.759998s,H11-P25624,373.790304s,canonical-H11
6,773.813501s,exact-cent transitions4,976.376943s,evidence126.589143s and
joint/proposal13.874491s. RSS1.136GB,CUDA allocation51,927,552B,2GiB artifact,
GPU-free,trailer-absence,true-model fixed-row isolation and zero-science gates all
passed.

F8R1C1 census/root/belief/solver/E0/E1/teacher/checkpoint/Slumbot/official counts
are all0. Never rerun,extend,tune or add a performance probe to F8R1C1. This is a
resource NONPASS before science,not evidence against exact-V5.5 CFR/BC. Same-family
re-ranking selects materially revised F8R2 as new science:4,096 census hands with
28,672 decision cap,eight fixed street-by-actor roots,two replicas with2,048
iterations,solver continuation cap8 followed by a separately frozen passive exact
call/checkdown/runout continuation,E0 2,048 and sealed E1 4,096 paired tapes per
root,and a fixed-root paired analytic one-sided confidence bound replacing the
100,000-bootstrap estimator. It retains rho1/8 full-joint mu/q and permanent
H11-P256 lanes. Frozen F8R1C1 rates project approximately4,808--5,110s,below the
21,600s admission limit. F8R2 requires fresh preregistration and independent
preimplementation audit;it is not a correction or continuation of F8R1C1.

Latest formal H11 remains -100.2475bb/100,CI95[-112.4067,-88.0883];latest complete
quick5k and last screened checkpoint remain CT003 -145.462bb/100,
CI95[-227.9171,-63.0069]. Last behavior change CT003;consecutive valid external
nonimprovement windows1. Rank1 exact-V5.5 teacher;rank2 critic/Qboost open but
resource-deprioritized;rank3 adaptive league;rank4 resolver. All four families
remain open;eligible checkpoints0;formal-claim hands0;strength L0;route exhaustion
false;goal ACTIVE. LRFT ledger SHA
`41a253089ac72f17f6ffc544ac6a1306b232fe4304bd784dccc429005ba51a10`.
Next is one fresh F8R2 preregistration plus independent preimplementation audit.
No model,resource benchmark,census,root,belief,solver,evaluation tape,teacher row,
checkpoint,Slumbot or official hand before that audit PASS.

Historical F8R1 update (superseded by the state above): identity/token were
`b35078ee7ad2ab123d5f9b0770538793d14e7b9dfbdbb51cc7897df93e2d3198` /
`b35078ee7ad2ab123d5f9b0770538793`. Preregistration SHA
`716c074f755d1a377e8752013025392721716d8a456115e7367485afa068b616`
freezes a minimal fixed-eight-root mechanism screen:16,384 canonical-H11 census
hands with114,688 decision cap,one blind root per street×actor cell,two disjoint
8,192-iteration importance external-sampling MCCFR+ replicas,source-hole proposal
rho1/8,one endpoint,E0 4,096 and sealed E1 8,192 paired tapes/root.

The primary claim is conditional only on those eight frozen roots/source holes:
candidate-root minus canonical-H11-root paired value under the same post-root
H11-P256 continuation,with E1 one-sided95% LCB>=+0.20bb/reached-root. It cannot
claim learner-root population uplift,GTO,NashConv,exploitability,teacher-asset
eligibility,checkpoint authority,Slumbot improvement or strength. PASS can only
authorize a separately registered broader F64R2 design.

Canonical root/belief H11 uses fixed batch256/index/padding and one CPU-f64
logits/probability/CDF routine. H11-P256 is separately defined by permanent512
lanes,two fixed batch256 chunks,no compaction,profile-independent paired lanes and
a73-step Latin translation;every logical branch occupies every physical position
exactly16 times. Exact upper work is672,896 network calls,172,261,376 rows and
84,000,768 exact-cent transitions.

The first instantiated preregistration audit is a frozen partial-output serialization
failure after `numpy.bool_`;source/partial SHAs
`22a05e170e42c7efdc9583622d2102bade57580fda2ecb49d1e4b3c14cbd2c3b` /
`0a308d7caaa5f769d5bce353e675fdc348d85f893faa746f2bbc80e1e11017ae`.
Its sole fresh C1 changed only native scalar serialization and output path;source/
result SHAs
`7e64ff98cdbc51e317d8d0af4ee545ebbe0792c16398d37c56794b7d0c267b6c` /
`d29d30681ea87f90d87e05084630ae9f944383a216c4f619fca0fc2b8b90198c`;
PASS10/10 independently instantiates the probability,RNG,mu/q,regret,root-average,
lane,pairing,confidence and exact-work contracts. Fresh implementation is authorized.

LRFT-F64 remains terminal structural-design failure SHA
`01a41d87ead30d0bec48d35c94efb5899d8c2227e222642b7401c0eed028f1c8`.
An in-flight52,236-byte runner draft materialized after the absence census but before
the stop message arrived;runner/freeze SHAs
`cc62907cb456523e88ce5b2fc34e721bb1e5b4c312fb4480f192f15b2abe81ca` /
`2e537ee3be11cc64e9b72a0810272f5ac45e0e660fd8ade5a5edacb3dc215ff4`.
It was never imported,compiled,tested or executed;preserve it read-only and forbid
F8R1 code reuse. All F64 model/network/scientific counts remain0.

VR002C1 remains terminal cause-UNPROVEN after3,064,100/5,000,000 hands;its partial
checkpoint is permanently ineligible and no quick5k is due. VRP-P01 remains terminal
resource NONPASS. LRFT-I00/I00C1 remain terminal interface NONPASS and forbidden
runtime dependencies. Latest formal H11 remains -100.2475bb/100,
CI95[-112.4067,-88.0883];latest complete quick5k and last screened checkpoint remain
CT003 -145.462bb/100,CI95[-227.9171,-63.0069]. Last behavior change CT003;
consecutive valid external nonimprovement windows1. Rank1 exact-V5.5 teacher;rank2
critic/Qboost open but resource-deprioritized;rank3 adaptive league;rank4 resolver.
All four families remain open;eligible checkpoints0;formal-claim hands0;strength L0;
route exhaustion false;goal ACTIVE. LRFT ledger SHA
`49bad946d8c1dd12c0854a440518ec8f865de3891fa3d5e305f82ab54d9e9d19`.
Next is finish the fresh-from-scratch F8R1 implementation plus independent no-model
implementation audit. Only audit PASS may authorize one zero-science exact-kernel
resource admission projecting all registered work below21,600s,20GiB RSS,6GiB CUDA
allocation and2GiB artifacts. No census,root,belief,solver,evaluation tape,teacher
row,checkpoint,Slumbot or official hand before resource-admission PASS.

## History Pointer

The predecessor AGENTS.md chronology is preserved at
`reports/AGENTS_snapshot_20260723_pre_accelerated_execution_82954eb0.md`. Its exact
pre-migration SHA256 was
`82954eb0f569c1c60d1882cb3292cd92d891641ed4e7be2158ee58f6334e8f62`;
the archived copy differs only by the `Archived` heading and has SHA256
`c253771d306f045442d3d7d5a62136bd9c8296b6d4c79c078128ed0f6608f872`.
Detailed chronology remains in immutable experiment reports, snapshots, and
`reports/v5_experiment_ledger.md`. Historical instructions are evidence only.
The immediately preceding current state is preserved at
`reports/AGENTS_current_state_snapshot_20260723_rs009_raw_qualification.md`; its
source `AGENTS.md` SHA256 was
`7527f7925f692c91fcc8a8da767f7c422cb9c3533da871e12f73fb79f5e50a25`.
The quick5k-authorized predecessor state is preserved at
`reports/AGENTS_current_state_snapshot_20260723_rs009_quick5k_authorized.md`; its
source `AGENTS.md` SHA256 was
`eeb898fa0e502ba51b304b1c65041ac370d97f2bdf18f36563f509d329419d2d`.
The immediately preceding RS009-terminal current-state meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_lg003c1_control_screen_f95eb513.md`;
its source `AGENTS.md` SHA256 was
`f95eb5139bfa4eb727987aae4406b8e8a22b5cef240cf226f928c74cb1827ab3`.
The immediately preceding control-screen-active meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_lg003c1_treatment_993cabc4.md`;
its source `AGENTS.md` SHA256 was
`993cabc42c1889850db5eacff3d8c19d1e8c9fccb8b34dd19206c9aec4c9c68c`.
The immediately preceding treatment-active meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_lg003c1_judgment_adc601be.md`;
its source `AGENTS.md` SHA256 was
`adc601be84f720bc1abec09f8ea55f1bcdfadd64faf9f1bd11a78f9163847611`.
The immediately preceding post-LG003C1 meta-review meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_tn001_judgment_8383b988.md`;
its source `AGENTS.md` SHA256 was
`8383b988f5b71dc8e00911bae228893535ba071c73578494852af188a5e7e6d0`.
The immediately preceding TN001-to-opponent-league meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_lg004_judgment_0793adda.md`;
its source `AGENTS.md` SHA256 was
`0793adda0f944b9cdc16a73e3e094d5a76cbd7a93722496109716f05bd3fc9d9`.
The LG004 compact ledger shard SHA is
`ff71bcbb51db32bd55b972fcf887d0046494b23832dba6194d4bb69bb8148948`.
The immediately preceding LG004-to-CT003 current-state meaning is preserved at
`reports/AGENTS_current_state_snapshot_20260723_pre_ct003_judgment_d708f2ee.md`;
its source `AGENTS.md` SHA256 was
`d708f2ee1a1d5944cece7b1e1a961684d8e3f06a1c863089bfd252f2d6217db2`.
The archived snapshot SHA is
`01ab388e11e0600661dd25a57e5290e4754bf21dd64d532fa1d69c0b23ad8d31`.
The CT003 compact ledger shard SHA is
`e4d69207ec3e53600490469e6153b267c766d7f7b7de3634302dfa9686d46ee4`.
