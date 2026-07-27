# CardPilot Autonomous Research Charter

## Authority

This user-approved revision is effective 2026-07-26 and supersedes every conflicting
workflow, goal, stop clause, preregistration rule, route freeze, and earlier research
charter. Historical artifacts remain evidence only; they do not control future work.

The legacy pre-autonomy `AGENTS.md` is preserved read-only at
`reports/AGENTS_pre_autonomy_charter_20260725.md`, SHA256
`33c201f9bf90b571b7f39511b322021a758c95caafb011ae5836c526d2c39be5`.

## Training-Scale Objective

Build the strongest possible general 200bb heads-up no-limit Hold'em policy through
actual optimization of model weights. Prefer methods and representations that can
later extend to six-max. Slumbot is an independent external benchmark, not the object
on which hand-written behavior is designed.

The final goal is to defeat the strongest publicly testable poker bot of its time with
rigorous evidence and solve poker decisions in real time.

The research path should scale training through approximately 10M, 50M, 100M, 250M,
500M, 1B, and paper-scale 2.7B environment hands when the learning curve and available
hardware justify continuation. These are optimization milestones, not reasons to run
a clearly broken configuration unchanged. When a method fails, improve or replace it,
restart its accounting clearly, and continue toward paper-scale training.

The formal Slumbot success bar remains one frozen trained policy completing at least
100,000 fresh Slumbot hands with bb/100 greater than zero, a 95% confidence-interval
lower bound greater than zero, and a reproducible hand-level evidence bundle.

## Structural Learning Principle

Do not ask only which checkpoint scored highest. Every experiment retrospective must
also answer: **what structural property of the poker learning system did this result
reveal?**

- Decompose results by seat. Persistent SB/BB asymmetry can indicate position
  representation, credit assignment, opponent-distribution, or shared-network
  interference rather than insufficient training volume.
- Treat successful seat-specialized models as evidence about architecture. Test
  position specialization, shared-trunk plus position-specific heads, and
  mixture-of-experts as scalable learned designs rather than relying on ad hoc policy
  splicing.
- Maintain stable, same-method training-volume curves at meaningful milestones such
  as 10M, 50M, and 100M hands. Do not attribute gains to more hands when datasets,
  opponents, architectures, or algorithms changed simultaneously.
- Slumbot may be a teacher and remains the external benchmark, but it must not define
  the policy's entire training distribution. Use self-play and diverse opponent
  leagues to measure and improve general poker strength.
- Quick5k is directional evidence, not a binary verdict on an idea. A losing result
  may still retain a hypothesis when it isolates a valuable mechanism, while a noisy
  positive result does not by itself justify the method.
- When additional training plateaus, explicitly test whether the limiting factor is
  the observation, action abstraction, network capacity, learning target, or
  optimization dynamics rather than simply adding more hands.
- Prefer representations and learned components that can extend naturally to six-max,
  without changing the current heads-up objective prematurely.

## Research Autonomy

Remain methodologically open-minded: do not default only to established training
recipes; actively test novel, high-information approaches that could produce
step-change gains, while requiring empirical evidence for retention.

The agent may, without further approval:

- change architecture, observations, action abstraction, critic, targets, advantage
  estimation, optimizer, training algorithm, reward shaping, curriculum, teacher,
  opponent league, resolver, inference topology, and hyperparameters;
- create new training data and checkpoints, run self-play, evaluate candidates, and
  replace unsuccessful research directions;
- use all available local CPU and GPU capacity while keeping the machine operational;
- repair and rerun control-plane failures when no valid scientific result was created;
- refactor or replace the research workflow, scripts, schemas, launchers, and
  verification code;
- choose experiments by expected external information gain rather than historical
  route order.

Old failed or provisional checkpoints may be inspected for diagnosis but must not be
silently presented as valid final candidates. The agent may start fresh from any
reproducible checkpoint it judges scientifically useful and must record that choice.

## Pure Training Contract

- A reported model improvement must come from changed learned weights produced by a
  documented optimizer, training dataset, self-play process, or distillation run.
- The deployed policy must choose actions from the trained network. Evaluator-side
  action overrides, hard-coded hand charts, forced folds/calls/raises, call guards,
  opponent-specific rules, and procedural strategy profiles are diagnostics only and
  are ineligible for trained-model, promotion, or formal-strength claims.
- Teachers, CFR, heuristics, search, privileged critic information, and Slumbot data
  may be used during training. Their useful behavior must be distilled into the policy
  weights, and information unavailable to a player at decision time must not enter the
  deployed policy observation.
- CFR solver iterations and CFR distillation decision samples are not environment
  hands and must be reported separately. An abstract CFR asset may be used freely as
  an experimental auxiliary teacher, but it must not be described as exact GTO or a
  high-accuracy oracle without direct convergence evidence such as fixed-seed
  iteration curves, cross-seed agreement, representative held-out boards, and an
  exploitability/best-response estimate or comparison with a trusted solver. The
  current 200bb SRP asset (80K stochastic iterations per flop, 50 made-hand-strength
  buckets, three bet sizes, one-raise-per-street cap, and no measured NashConv) is an
  unqualified approximate teacher; its outputs and any model distilled from them must
  earn retention through held-out and external evaluation.
- Track both `new_training_hands` for the current run and
  `lineage_training_hands` inherited through checkpoints. Evaluation hands do not count
  as training. Offline decision samples, synthetic states, and teacher examples must
  be reported separately rather than converted into fictional environment hands.
- Every retained lineage should expose a learning curve across training volume using
  a stable internal evaluation suite. Architecture or algorithm changes are welcome;
  report their counters honestly instead of combining incomparable totals.
- A hybrid or manually patched policy may be retained for debugging, but it must be
  labeled `HYBRID_DIAGNOSTIC` and may not replace the best pure trained checkpoint.

## Fast Research Workflow

Discovery experiments do not require preregistration, independent audit, full
repository content addressing, immutable identities, full snapshots, or full hand
replay. They do require the lightweight launch-time code, configuration, and lineage
record described below so that useful results can be reconstructed later.

Each meaningful experiment needs only one compact record containing:

1. hypothesis and material change;
2. source checkpoint plus code/config identity;
3. new and inherited training hands, decision samples, runtime, and throughput;
4. learning-curve result and external result, if run;
5. retain, revise, or reject decision.

## Research Record and Retrospective Requirements

Research records are part of the experiment, not optional paperwork. Their purpose is
to make later comparison, failure analysis, reproduction, and research retrospectives
possible without relying on memory, terminal history, or inference from filenames.

- Create the compact experiment record when a meaningful run is launched, not only
  after it finishes. Mark it `PLANNED` or `RUNNING`, then update the same record to
  `COMPLETED`, `FAILED`, `INTERRUPTED`, `RETAIN`, `REVISE`, or `REJECT` as evidence
  arrives. A crash or interrupted launcher must not erase the intended hypothesis.
- Give every run a stable run ID and store or link its record beside the run
  artifacts. Maintain one lightweight human-readable index or ledger that links to
  the authoritative per-run records; avoid duplicating large logs into governance
  documents.
- Record the hypothesis, material change, reason for the experiment, comparison
  baseline, expected information gain, source checkpoint path and SHA256, lineage
  parent, and whether the deployed policy is `PURE_TRAINED` or
  `HYBRID_DIAGNOSTIC`.
- Capture a reproducible code/config identity at launch: Git commit, dirty-worktree
  status, the exact command or fully resolved configuration, launcher identity,
  random seeds, and SHA256 or a lightweight patch/copy for materially changed
  trainer, environment, network, evaluator, and configuration files. Do not assume
  that the current working tree will remain available later.
- Record the material runtime environment when it may affect reproduction: operating
  system, Python, PyTorch, CUDA, GPU, important package versions, device topology, and
  worker/process settings. This should be generated automatically and remain compact.
- Keep accounting units explicit and separate: target and actual
  `new_training_hands`, inherited and final `lineage_training_hands`, evaluation
  hands, offline decision samples, synthetic states, teacher/CFR samples and
  iterations, wall-clock runtime, throughput, and material CPU/GPU utilization.
  Independent lineages must never be added together as one policy's training volume.
- Record optimizer and learning method details sufficient to reproduce the weight
  update: algorithm, learning rates, schedules, reset/resume behavior, batch sizes,
  epochs, loss coefficients, clipping/KL rules, reward and target construction,
  curriculum, opponent/teacher mixture, observation and action versions, and which
  parameters were trainable or frozen.
- Preserve periodic training metrics and checkpoint-to-volume mappings needed for a
  learning curve. Use the stable internal evaluation suite at meaningful volume
  milestones, and record evaluator version, seeds, opponents, sample size, score and
  uncertainty so that curves remain comparable.
- Preserve every external evaluation, including negative and aborted results. Link
  the frozen policy hash, evaluator code/config identity, exact game contract,
  policy/inference mode, hand count, bb/100, confidence interval, session or seed
  structure, errors, and hand-level evidence location. Clearly label partial results
  and never silently replace them with a later run.
- At termination, add a concise retrospective: what happened, whether the hypothesis
  was supported, anomalies or engineering incidents, likely failure mode, comparison
  with the baseline and earlier milestones, retain/revise/reject decision, and the
  most informative next step. Failed and null experiments are valuable evidence and
  must remain discoverable.
- Resumes, restarts, repairs, algorithm changes, and architecture changes must link to
  their parent record and state whether counters continue or restart. Never merge
  incomparable hand counts or retrospectively invent missing values; use `unknown`
  and explain the gap.
- Prefer automatic capture in launchers, trainers, and evaluators. Start with a small
  in-progress record and enrich it asynchronously; recordkeeping must not block a
  valid run or consume more than the research-governance budget except when required
  to preserve a promotion or formal-claim candidate.

Path, import, quoting, serialization, launcher, checker, and reporting defects are
ordinary engineering bugs. Fix them directly and continue. They do not freeze a
scientific hypothesis or require a new identity chain.

Use lightweight deterministic tests during discovery. Full content-addressed freezing,
independent hand-level verification, and complete evidence bundles are required only
for a candidate entering a promotion or formal claim evaluation.

Do not spend more than roughly 10% of research time on governance, documentation, or
audit infrastructure unless it directly clears a measured blocker to training or
external evaluation.

As a non-binding research preference, after several concurrent discovery runs or
quick screens produce enough directional evidence, consolidate around the few most
informative pure-weight lineages and return most compute to larger environment-hand
training runs. Parallel exploration and additional screens remain allowed whenever
their expected information gain justifies them; this reminder is intended to reduce
fragmentation, not impose a route limit or approval gate.

## Evaluation Integrity

- Slumbot measures external heads-up strength; self-play and opponent-league results
  measure learning progress and generalization.
- Develop for generalizable poker competence rather than Slumbot-specific fit; Slumbot
  is an external measurement instrument, not the definition of the policy's target behavior.
- Do not use completed Slumbot evaluation hands to create direct action rules. They may
  motivate a new training hypothesis, which must then improve weights and be tested on
  fresh hands.
- Do not change game rules, the 200bb stack, evaluator accounting, or the pure trained
  inference contract to improve a score.
- Freeze a candidate before its promotion or formal evaluation.
- Preserve and report every external evaluation; never cherry-pick only winning runs.
- Do not tune on the final formal100k hand set.
- Quick5k and 20k are directional screens with uncertainty, not proof. Prefer external
  tests at meaningful training milestones rather than testing many tiny patches.
- Promote promising pure trained candidates to 20k and reserve formal100k for a
  plausible winner.
- Run the GTO Wizard test only after a pure trained checkpoint achieves at least
  +15 bb/100 over 100,000 fresh Slumbot hands with a positive CI95 lower bound.

## Resource and Safety Boundaries

The agent may maximize local hardware utilization and run unattended training.
Keep enough CPU, memory, and disk capacity for the operating system and evidence
preservation. Avoid uncontrolled output growth and retain the best reproducible
checkpoint before replacing large disposable runs.

Ask the user only before spending money, using or exposing secrets, performing
destructive actions against material data, contacting people, changing the formal
evaluation contract, or exceeding available local resources. Normal in-workspace
implementation, training, testing, evaluation, and reversible cleanup are authorized.

## Current State

The research program is ACTIVE and authorized to proceed immediately. No checkpoint
has passed the formal Slumbot bar.

The 2026-07-26 audit found that the PokerSkill-SB and river-pair-fold candidates have
the same 80 learned tensors as their Stage4 source and obtain their behavior changes
from evaluator-side strategy overrides. They are `HYBRID_DIAGNOSTIC`, not trained
model improvements. The latest located pure-weight Stage4 external reference is 9,998
Slumbot hands at -30.1054 bb/100, CI95 [-59.9196, -0.2913].

The immediate priority is to select a reproducible pure checkpoint or start fresh,
remove all behavior overrides from the claim path, maximize stable training
throughput, and build a real performance-versus-training-volume curve toward 2.7B
hands. Governance-heavy Qboost work is optional and must not delay useful training.
