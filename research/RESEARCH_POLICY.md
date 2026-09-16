# Efficiency-first AlphaHoldem research policy

Adopted with user authorization on 2026-09-04. This continues existing research,
not a reset of experiments, policies, training counters, or the external goal.

## Outcome and scope

The acceptance target remains one complete frozen execution policy at >=100,000
fresh Slumbot hands, positive raw bb/100 and a valid 95% CI lower bound above zero.
Freeze weights, observation/action contracts, legality mapping, execution mode,
runtime and statistical stopping rule before formal testing. Development tests
cannot be relabeled as final blind tests. Do not train directly on Slumbot action
labels or add opponent-specific action rules. Slumbot success is not proof of
universal optimality; assess held-out heterogeneous opponents and relative gains
in both seats separately.

## Resource decisions

Maintain one primary training lineage family and at most one major algorithmic
control. Prioritize experiments by their expected impact on the next compute
allocation decision, not record count or local novelty. Infrastructure fixes are
not extra algorithm research branches. Use geometric multi-seed learning curves;
small smokes establish contracts, updates, stability and short-term mechanisms,
not whether long-run learning can ever succeed. Distinguish causal failure,
replicated broad regression, insufficient evidence and insufficient scale.

Scale toward paper-sized work only when curves and measured wall-clock costs
support it. Preserve a frozen reference but do not equate low policy drift or
low training loss with poker improvement. Calibrate internal rankings against
predeclared external development checkpoints; avoid selecting lucky 5k pilots.
Assess actor scope and opponent diversity using matched controls, not assumptions.

## Execution and evidence

Automate accounting, artifact hashes, resume preflight and completion detection.
Use the researcher for meaningful changes, failures and milestone decisions, not
repeated unchanged polling. Log meaningful experiments with experiment_log.py.
At each major milestone report strength evidence, compute cost, uncertainty and
the next decision. Preserve all prior raw evidence and correct claims append-only.

Separate terminal execution hands, unique deterministic deal identities, hands
that generated trainable transitions, and replay samples. Exact optimizer/replay
restoration does not establish full rollout/RNG equivalence. Every restart must
account for earlier attempt namespaces, worker cursors and any unknown crash
suffix. Label statistical continuation explicitly; never count skipped indices.

## Immediate priority

The current 4M static-KL experiment has evidenced Seed2 recovery deal-prefix
reuse. Do not modify live training source. Preserve outputs, quantify the overlap,
and amend interpretation before treating its three-seed result as clean replication
or automatically allocating 8M. Implement and test fail-closed resume prevention
in isolation first; integrate only at a safe process boundary. No completed work
is to be silently discarded or rerun.

The one-shot 4M followthrough is documented in
`research/experiments/v6-static-current-kl-4m-scale-20260904/guarded_followthrough_contract.md`.
When its exact owner PID is live, it owns that experiment's logger and frozen
Python dependencies; do not create a competing writer or edit those dependencies.
If all 4M targets finish, complete the existing frozen evaluation with the unchanged
runtime before production cutover. If a natural runtime boundary is below target,
the followthrough stops: integrate and qualify managed resume before continuing
only the remaining hands. This scheduling rule never authorizes automatic 8M scale.

## Completed incident status (verified 2026-09-06)

The "Immediate priority" section above records the 2026-09-04 incident response,
not an unfinished recovery task. The existing
`research/experiments/v6-static-current-kl-4m-scale-20260904/experiment.json`
is COMPLETED with its repeated-deal deviation, original audit failures and corrected
interpretation preserved. The subsequent
`research/experiments/v6-managed-trainer-resume-integration-20260904/experiment.json`
is also COMPLETED: production managed resume passed 379 regressions and real GPU
namespace/optimizer/replay/counter checks. This qualifies statistical continuation,
not bitwise worker RNG/in-flight equivalence, and does not erase the earlier reuse.

Do not reopen or rerun those completed experiments merely because a persistent
goal or historical note still names the 4M incident as its immediate priority.
Use the current generated `research/EXPERIMENTS.md` and exact live process identities
to locate ongoing work. The ownership, immutable-evidence and resume safeguards
above continue to apply to every active run. This dated clarification changes no
acceptance criterion, training allocation, frozen policy or experimental result.
