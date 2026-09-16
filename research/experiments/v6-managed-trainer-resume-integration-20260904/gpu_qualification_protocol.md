# Current-recipe GPU qualification, fixed before 4M outcome inspection

This completes the existing managed-resume integration experiment. It is not a
new learned-method branch, a strength evaluation, or authorization to scale to 8M.
Do not execute until the guarded 4M owner, launcher, trainer and evaluator children
are terminal. The authoritative scheduling order is RESEARCH_POLICY.md and
guarded_followthrough_contract.md, superseding the older staging note's order.

## Fixed inputs and scope

Use the already-terminal, incident-unaffected Seed1 4M checkpoint, irrespective
of its eventual evaluation rank:

- `../v6-static-current-kl-4m-scale-20260904/seed1/latest.pt`
- SHA256 `7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f`
- initial physical count 4,197,976; iteration 882.

Install the reviewed staged trainer only at the safe boundary, retaining the
original source and applying its diff with apply_patch. Expected staged SHA256:
`1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b`.
First run the full `python -m pytest -q scripts/alpha_holdem` regression suite
and the focused logger/CI tests already required by the research workflow.

Then compare only single1 and multi8 using the inherited production recipe:
12 workers, 4096 transition-bearing hands/update, sampled hero, all policy heads
plus critic_v2, current-to-reference Standard10 KL coefficient 1, PPO epochs 2,
target KL .01, minibatch 16384, replay depth 2/ratio .5, loss-K-best K=5,
adaptive eight-group assignment, three original anchors, self-play fraction .25,
and preserved optimizer LR .0001. Keep the original Seed1 training/worker seeds,
deal start, run identity and SHA-bound assignment/metric prefixes. Each launch
must allocate a fresh durable namespace; no deck pairing or uninterrupted worker
RNG equivalence is claimed.

## Budget and order

Fixed ABBA order: single1 attempt1, multi8 attempt1, multi8 attempt2, single1
attempt2. Both first attempts fork the identical frozen parent. Each second
attempt resumes its own arm's first terminal checkpoint with its complete raw
prefix. Each attempt targets **8192 additional physical hands**, stopping at a
complete PPO boundary (actual overshoot and unconsumed terminal tails reported).
Each has a 600-second trainer runtime guard. Below-target completion or any
mechanical failure stops the diagnostic for inspection; no automatic retry,
deleted output, reused namespace or reset counter is allowed. Existing output
directories must be refused, not overwritten.

## Required evidence

Capture each exact argv and source/input SHA256, wall-clock start/end, terminal
manifest, initial resumed checkpoint, raw metric/assignment prefix and appended
suffix, final checkpoint and durable attempt receipt. Verify initial weights,
optimizer states/LRs, replay entries/RNG/cumulative draws, iteration, both hand
counters, pool snapshots/history and the available main RNG. The legacy parent
has no main RNG and must be explicitly labeled bootstrap. The second attempt
must preserve CPU/Python/NumPy **and CUDA** RNG snapshots; worker action RNG and
in-flight rollouts remain statistical continuation. Verify updates and replay
draws advance, all new metrics are finite in core losses, all four namespaces
are distinct, source/prefix/parent hashes remain unchanged, and workers exit.

Report diagnostic execution hands separately from retained update hands and
research-lineage hands. Do not count copied prefixes again. Do not count this
work as Slumbot/internal strength evaluation, and do not promote its checkpoints.

## Cost decision

Primary speed is total new physical hands divided by measured subprocess wall
seconds, including startup, updates, checkpointing and worker shutdown. Also
report transition-bearing throughput, within-attempt metric timestamp rates,
and total runner overhead. Do not substitute trainer collection-only h/s.

Multi8 is provisionally throughput-qualified only if all mechanics pass and its
pooled subprocess-wall throughput is at least 1.25x single1, with the advantage
present separately in both first and resumed attempts. Otherwise retain single1
and inspect the evidence; do not begin a broad parameter search. This ordered,
single-parent diagnostic is not a causal confidence interval, multi-seed strength
test or guarantee of long-run throughput. Future authorized training must confirm
realized wall-clock cost and preserve the method's predeclared strength gates.

Planned execution entry point:
`python research/experiments/v6-managed-trainer-resume-integration-20260904/run_gpu_resume_qualification.py`

Its `--preflight-only` mode is read-only and must report ineligible while the
existing guarded pipeline is live. No GPU workers or new evidence are created
by preflight. This document records a plan, not a claim that GPU tests passed.
