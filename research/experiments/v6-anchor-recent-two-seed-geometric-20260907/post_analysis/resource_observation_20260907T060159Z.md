# Read-only concurrent GPU-load observation

Observed while the registered controller PID48468/create1788760722.5186431
and Seed1 control trainer PID15224/create1788760730.146436 remained live.
No training/runtime/source/checkpoint changes or competing logger writes made.

At 2026-09-07T06:01:59Z, Windows GPU engine formatted counters reported
training PID15224 at6% and a concurrent game process PID60216 at80% on the
same phys0 3D engine. An earlier sample reported7% and66% respectively.
The GPU aggregate query reported100% utilization and10557MiB used.
These are transient WDDM engine samples, not additive whole-device attribution
or a controlled causal throughput experiment. They support concurrent resource
competition as a contributor to slower wall time; they do not establish a
policy-strength effect or a trainer performance regression.

At retained iteration2666, physical cumulative counter12611123 minus original
parent12595669 equals15454 new physical executions. Iterations2665/2666 log
collection times36.6/32.9seconds and transition-bearing collection rates113/125
hands/sec. These rates are not aggregate physical executions per wall second.

Read-only commands:

```powershell
nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Where-Object { $_.UtilizationPercentage -gt 2 -and $_.Name -match 'pid_(15224|60216)_' } | Select-Object Name,UtilizationPercentage | ConvertTo-Json
```

Do not terminate or reconfigure unrelated user applications. Continue the
registered physical targets with the existing7200second natural runtime boundary;
review any incomplete boundary without resetting counters or replaying earlier
hands. Do not extrapolate paper-scale throughput from this contended interval.
Attach this observation to the existing experiment after its single log owner is
terminal; it is not a separate algorithm experiment or an instruction to that owner.
