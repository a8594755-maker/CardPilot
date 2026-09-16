# Shared-machine throughput observation, not algorithmic attribution

Read-only observation during Seed1 half-rate stage1,2026-09-05 approximately
22:31-22:35UTC. No live source/configuration, process priority, other application,
training budget or experiment logger was changed. Attach this note to the same
record after its controller exits; it is not a separate algorithm experiment.

## Two completed full-rate cells

Source directories relative to research/experiments:

- v6-current-kl-representation-pilot-20260905/seed1_full_stage1 (earlier cell).
- v6-full-step-size-1m-continuation-20260905/seed1_full_stage1 (current cell).

| Observable | Earlier | Current |
|---|---:|---:|
| Actual new physical hands |262159|265240|
| Transition-bearing new hands |226638|239194|
| Training subprocess wall seconds |504.2283373|1068.6800480|
| Actual physical hands/second |519.921196|248.194023|
| Completed iterations |55|58|
| Sum of reported collect seconds |297.5|727.8|
| Sum of reported PPO seconds |61.3|114.1|
| Mean reported inference batch |20.601818|20.45|

Counts/wall times come from each verification.json; iteration/phase timings and
batch means come from its closed stdout.log. Log timing values are rounded, and
are not a profiler breakdown of every overlapping worker activity. In particular,
do not interpret wall minus reported phase sums as a precisely identified I/O cost.
These are different training endpoints/deal streams/times, not a matched hardware
benchmark. Current per-parameter Adam step increase is218 for all86 parameters;
the earlier cell had196. More actual updates do not alone explain all wall change.

Closed stdout SHA256:

- Earlier:f91223d6e1a866d0d05a63199c98d8a22356e621e087d7b63daa16ce3a2b4a6f
- Current:e12b1aa29a01e6cd892c0af17348f41d7b126ad60ad9ad3af57a89eb059b342d

Recompute phase totals with regex `collect=([0-9.]+)s ppo=([0-9.]+)s` and mean
`inf_bs=([0-9.]+)` over complete iteration lines in these immutable logs. There
are55/58 such matches; no inherited prefix is in stdout.log.

## Limited live hardware context

One nvidia-smi snapshot during the half-rate job showed P2,SM2805MHz,
memory10251MHz,power79.02W,temperature49C, GPU utilization30%,used10061MiB.
One Windows processor counter showed30% processor time. These instantaneous,
asynchronous observations are not averages or proof of a bottleneck. The GPU
process inventory included other graphical applications; no other processes were
closed, suspended or inspected for application content. WDDM nvidia-smi per-process
memory was unavailable. A later Windows GPU memory counter for the live trainer
PID19592 showed5107707904 dedicated and85983232 shared bytes. Do not infer GPU
paging, thermal throttling or a specific competing application as the cause.

Relevant read-only snapshot commands:

    nvidia-smi --query-gpu=pstate,clocks.current.sm,clocks.current.memory,power.draw,temperature.gpu,utilization.gpu,memory.used --format=csv,noheader
    nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader
    Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter "Name='_Total'" | Select-Object PercentProcessorTime,PercentIdleTime
    Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object { $_.Name -match '^pid_19592_' } | Select-Object Name,DedicatedUsage,SharedUsage,TotalCommitted

The counters would describe a new observation if rerun; the specific transient
hardware snapshot is not claimed reproducible. The closed training-cost evidence
is reproducible from the retained files.

## Resource interpretation

Retain actual measured wall costs per cell instead of assuming the prior~633/s
aggregate rate continues. The cause of the approximately2x wall-rate difference
is unresolved. Shared-machine resource conditions are a possible confound for
cost comparisons, not evidence either learning rate produces weaker poker. Both
arms still receive fixed physical-hand budgets, with realized optimizer dose
reported separately. Continue the unchanged preregistered experiment. If slower
throughput persists and strength curves justify substantial scale, assess dedicated
resource conditions and a controlled throughput profile at a later safe boundary
before extrapolating months of training. This note neither starts such a profile
nor authorizes additional resources or changes to other applications.

## Closed evaluation cost observation,23:37UTC

The first current evaluation finished cleanly before this comparison. Compare
the previous pilot's job_eval_seed1_full_stage2 and eval_seed1_full_stage2 with
the current experiment's job_eval_seed1_full_stage1 and eval_seed1_full_stage1.
Both actual command.json files use the same evaluator, CUDA,2048 pairs per anchor,
four identical frozen anchors and the same greedy/legacy-v4/physical200bb
contract. Parents, treatments, evaluation deck seeds and execution times differ;
this is not an isolated hardware or algorithm throughput experiment.

| Observable | Previous pilot stage2 | Current stage1 |
|---|---:|---:|
| Executed evaluation hands |32768|32768|
| Control plus treatment decision queries |189443|179154|
| Subprocess wall seconds |494.2189477000|1224.5196869000|
| Executed hands per second |66.3025975683|26.7598800987|

Current wall time is2.477686646 times the previous cell despite fewer reported
decision queries. Count differences therefore do not explain the slowdown by
themselves; neither do these aggregate data identify a particular competing app,
CPU bottleneck, GPU launch latency, paging or a source-code regression. The Python
process's sustained CPU use is NOT evidence evaluation is CPU-only: its frozen
command explicitly selects CUDA. No instrumentation was inserted into the live
evaluator, and no process priority, thread count or other application was changed.

The current four training cells took3745.0764722 subprocess seconds. Four eval
cells at this single observed rate would take4898.0787476 seconds, excluding
controller overhead. This is a conditional planning illustration, NOT an ETA:
only the first eval cell is complete, and earlier measurements varied. The final
report must use each actual termination.json rather than this extrapolation.
Evaluation cost can be material even when its hand count is lower than training.
Retain this evidence when choosing the next safe-boundary resource profile and
budget; do not shorten this preregistered evaluation or change its runtime.

Recompute the table by reading each summary.json and job termination.json with
PowerShell Get-Content -Raw | ConvertFrom-Json: evaluation_hands / wall_seconds is
the rate; sum anchors[*].control.decisions + anchors[*].treatment.decisions for
the query counts. Immutable supporting SHA256 values:

- Previous job termination:e25d618d04626a0ed26aa1bbc316f96cf27743c2e60e1df32fa015aa9f7e6eec
- Current job termination:5ba1f05324eb224f9dc0708d8a1a8cb5e2f651e8bbe3db9f945ccbb67f53723e
- Previous summary:a4b8414a9f12f9bc73ffce3bd866a233bebccf61e34248f617a4e0a8027863c3
- Current summary:1496403dc950b10c3a975d6e9a4907917d18a08b4bb11de90b2659eddbcb7d77

Read-only call-path inspection at00:00UTC confirms v6_elo_eval.py greedy_action
constructs four device tensors for each decision, forwards a batch of one, then
copies nine logits back to CPU for legality selection. summarize_models plays
the two seats and every deck serially. network_hybrid_h1.py forward also computes
the scalar value that this evaluator discards. These are concrete profiling
locations, not measured bottleneck shares or explanations of the between-run
slowdown (the earlier evaluator has the same structure). Any future batching,
actor-only forward or CPU/CUDA comparison requires fixed-state/action/trajectory
contract validation and measured timing after the owner exits. No candidate
runtime or parallel GPU performance workload was launched here.
