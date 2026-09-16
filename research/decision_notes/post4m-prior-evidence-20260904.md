# Prior evidence for the post-4M compute decision

Written on 2026-09-04 while the original Seed3 trainer and guarded 4M
followthrough remain live and before any 4M endpoint evaluation. This is a
zero-new-hands literature/history review, not a new training experiment, a
changed promotion gate, or authorization to start another run. Attach it to the
existing 4M experiment's final analysis only after its logger owner terminates.
Do not edit that live record or its frozen dependencies to attach it now.

## Decision that the pending evidence must inform

Finish every originally registered endpoint, anchor, seat and evaluation budget.
Retain Seed2's training-deal reuse and report all three seeds plus the fixed
incident-unaffected Seed1/Seed3 subset. A fresh namespace in a future continuation
does not retroactively make Seed2's inherited lineage a clean replication.

The next allocation should decide between further investment in the existing
learned method and one consequential matched method control. It should not be a
new collection of small PPO, imitation, gate or action-patch variants. Production
managed-resume qualification remains required before any new training.

## Evidence that should prevent repeated or overstated conclusions

| Existing experiment | Relevant observation | Decision-level interpretation |
| --- | --- | --- |
| `v6-static-current-kl-2m-scale-20260904` | Pooled 1M-to-2M slope -1.1373 bb/100, paired CI [-4.6040, 2.3295]; two positive seeds, one broad reversal; no breadth-positive seed. | The 4M stage was justified as another geometric observation, not established strength. Evaluate the registered breadth criteria, not only a count of positive seed point estimates. |
| `v6-nashpg-moving-reference-geometric-20260903` | Six 65k runs; moving reference refreshed after every PPO call. Final moving-minus-static pooled delta -0.6633, worse in two seeds; one moving seed exceeded TV .08. | Evidence against this interval-1 local intervention. Not a faithful NashPG replication and not evidence against all long-horizon regularized self-play. |
| `elo-kbest-league-pilot-20260830` | About 264,560 training and 52,448 evaluation hands; 4/12 positive paired rows, mean delta -0.0255; every paired CI crossed zero. | Little evidence of useful selector-only gain at that budget. Do not repeat it as a new idea. Do not turn inconclusive small-scale deltas into a general impossibility claim. |
| `v6-legacy-fresh-zero-elo-smoke-20260901` | 34,238 physical hands; very large improvement against the random initial actor but Standard10 transfer delta -161.21, CI [-283.35, -39.07]; first-update KL about 1.074. | Explicit early optimization/transfer risk in that recipe. Beating a random initial policy is not a sufficient strength proxy; it does not settle what a stable long-run recipe can learn. |
| `v6-legacy-standard10-curriculum-elo-survivor-selection-20260901` | Outcome-blind top-rated ELO survivor lost breadth versus the terminal actor: pooled delta -51.30, CI [-88.12, -14.49]. | In-family tournament rating did not supply a general-strength checkpoint selector at this scale. Preserve the distinction between opponent selection and external strength. |
| `v6-public-opponent-external-alignment-audit-20260902` | Six frozen policies: public behavior-clone proxy Spearman -0.543 and Pearson -0.593 versus external results; only 1/9 externally decisive pair orderings correct. | An actual ranking-proxy failure, not merely too little training. Do not use this proxy for checkpoint selection or scale authorization. |
| `v6-full-network-learning-curve-20260831` | Corrected-contract full-network run reached 265,430 physical hands; post-hoc final-minus-first-archive training-anchor mean +192.36 but held-out mean -185.85, CI [-350.05, -21.65]. | Simply unfreezing the trunk is not an untested guaranteed improvement. The result is regimen-specific and post-hoc; it does not reject representation learning in general. |
| `v6-representation-full-greedy-bridge-fresh5k-20260903` | Unchanged older full-network weights at corrected greedy execution: -68.8218 bb/100, CI [-147.2755, 9.6319], missing the predeclared point floor. | The old checkpoint did not transfer under that bridge. It is not proof that all full-network methods fail; its training contract differed from the current one. |
| `v6-static-current-kl-highpot-critic-calibration-20260904` | 24,576 new internal hands; high-pot MSE change and specificity intervals crossed zero. | No demonstrated critic-worsening mechanism supporting a high-pot resampling or critic-reset intervention. Losing-hand attribution is not an action label. |

The individual immutable experiment records and their linked raw evidence are
authoritative. These summaries do not overwrite their original decisions or
relabel completed development hands as new experiments. The historical sampled,
greedy and corrected-bridge Standard10 scores are separate execution contracts.
The historical -11.4275 point reference is not an exact current-runtime result.

## Primary-source fidelity checks

AlphaHoldem reports 8 TITAN V GPUs and 64 CPU cores, roughly 2.7B hands, a fully
learned network and competition/ELO survivor selection. The present single-GPU,
head-only, static-reference, loss-selected league is a local derivative, not a
paper reproduction. Matching the paper's minibatch size alone does not align
these other mechanisms or its wall-clock cost.

Source: [AlphaHoldem, AAAI 2022, experimental setup and model selection](https://cdn.aaai.org/ojs/20394/20394-13-24407-1-2-20220628.pdf).

Practical NashPG gathers trajectories under the current joint policy, trains
both players and holds references through an inner optimization phase before
refreshing them. Its paper uses 10,000 inner updates for non-Kuhn settings; the
local interval-1 experiment tested a different timescale and retained a mostly
historical/fixed-anchor league. The paper explicitly disclaims a formal
convergence guarantee for practical NashPG. Its poker setting is 200 chips with
blinds 1/2 (100bb), not this project's 200bb acceptance contract.

Sources: [NashPG v3, algorithm 4 and experimental appendix](https://arxiv.org/html/2510.18183v3),
[author implementation, outer-loop reference refresh](https://raw.githubusercontent.com/ntu-agents/nashpg/main/train/nash_pg.py).
The repository URL is mutable and was inspected read-only; it is not a frozen
implementation artifact or an instruction to install or execute upstream code.

These fidelity differences nominate possible substantive controls, not evidence
that copying any one component will produce a winning policy. Select at most one
major control after the pending 4M evidence and measured costs are available.

## Cost and evaluation discipline

- Reuse the staged single1/multi8 current-recipe qualification after the complete
  guarded pipeline terminates. Its outcomes have not yet been observed. Count
  measured subprocess wall time, startup/update/save/shutdown overhead, physical
  executions and transition-bearing hands separately. Do not promote diagnostic
  checkpoints or claim a speedup from a past different recipe.
- Avoid projecting a fixed completion time from instantaneous collection h/s.
  Seed3's recent metric intervals slowed during concurrent desktop load; a
  resource snapshot does not establish the cause. Do not close other user apps.
- If the internal curve supports more investment, consider a separately
  preregistered external development calibration before a large new allocation.
  Fix the endpoint selection rule and full execution contract before new hands;
  do not choose a lucky 5k winner or call development hands the final blind test.
- A positive raw point estimate over 100k hands is not sufficient for the final
  goal. Predeclare the formal sample size, stopping rule, independence checks and
  valid CI assumptions. The current CI arithmetic helper alone does not prove
  frozen-policy provenance, session independence or absence of optional stopping.
- Keep all algorithm conclusions distinct from software reliability conclusions.
  Passing resume tests and accumulating physical hands are useful prerequisites,
  not evidence of a stronger or sustainably profitable poker policy.

## Handoff

Once `EVIDENCE_READY_FOR_RESEARCH_ANALYSIS` is accompanied by OS-confirmed owner
and child termination: inspect the actual original and deviation-aware reports,
finish that same record with accounting/hashes and the explicit scale decision,
then integrate and qualify managed resume. If the natural training boundary is
below target, follow the existing managed-continuation contract instead. Nothing
in this note changes the pending run, its frozen inputs, or either handoff rule.
