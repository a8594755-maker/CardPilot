# Explicit v2 evaluation handoff adapter

This prospective scheduling-only adaptation is staged while the frozen 4M
evaluation is live. It does not authorize production integration or GPU work now.
The original GPU protocol and runner remain byte-identical. Use the new entry
point only after the successor evaluation owner/children have naturally exited,
all original evaluation/drift evidence is complete, and the same 4M experiment
record has been analyzed and finished.

The original guarded v1 owner stopped, correctly, on a capped-history audit
failure. Archive/assignment replay subsequently proved the failure came from the
old audit's completeness assumption. A separately qualified v2 owner continues
the untouched evaluations. Do not rewrite v1's failed status into a passing one.

`gpu_qualification_v2_handoff.py` adds an explicit proof of the successor's
termination and completed evidence. It can remove only the exact obsolete v1
phase objection, and only when the v2 proof passes. All original process, other
GPU-owner, checkpoint, production-candidate, code, namespace and existing-output
checks remain active. Active v2 ownership between child jobs must also block.
It does not use evaluation scores to choose a policy or require favorable scores.

The adapter verifies the successor's frozen inputs, final aggregate/report hashes,
three-seed inclusion, 98,304 evaluation hands, 60,000 drift states, retained old
failures, and completed experiment accounting. After the intentional production
cutover it verifies the preserved old source copy against the historical hash,
while the original preflight separately requires the exact staged new source.
The old ownership/status, checkpoints, raw hands and completed results stay intact.

The actual diagnostic still delegates to the original runner: fixed Seed1 parent,
single1/multi8 ABBA, 8,192 additional physical hands per attempt, existing seeds,
full optimizer/replay/RNG/assignment evidence, 600-second guard, one new namespace
per launch, and unchanged speed/qualification decision. No reset or automatic retry.
The original output name remains gpu_current_recipe_v1; the adapter cannot reuse
an existing output. No checkpoint promotion or new strength claim follows.

Read-only check:
`python research/experiments/v6-managed-trainer-resume-integration-20260904/gpu_qualification_v2_handoff.py --preflight-only`

Execution, only after safe handoff, exact production integration and regressions:
`python research/experiments/v6-managed-trainer-resume-integration-20260904/gpu_qualification_v2_handoff.py`
