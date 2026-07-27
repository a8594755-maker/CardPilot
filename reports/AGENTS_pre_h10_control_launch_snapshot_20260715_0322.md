# CardPilot Agent Workflow

## Current Objective

Reproduce and extend AlphaHoldem for 200bb heads-up no-limit Hold'em with an end-to-end RL agent. The reference paper is Zhao et al., "AlphaHoldem: High-Performance Artificial Intelligence for Heads-Up No-Limit Poker via End-to-End Reinforcement Learning," AAAI 2022.

Primary target: beat Slumbot at 200bb. A valid win claim requires at least 100k Slumbot hands, bb/100 > 0, and 95% CI lower bound > 0. The stretch target is near the paper result: about +11.1 bb/100 vs Slumbot.

Do not claim V4/L5/L6 strength from training health, self-play reward, 2k diagnostics, or 5k quick screens.

Current authoritative update (2026-07-15): CAL-EXT-001 is terminal complete on the
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
