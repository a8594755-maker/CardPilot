# Shared-GPU observation during the first detached control cell

Read-only observation while exact controller57824/create_time1788676494.1425543
and trainer24424/create_time1788676510.2257097 remain live. No training source,
batch, priority, affinity, GPU settings or other application was changed. Defer
this note and its commands to the experiment logger until sole-owner exit.

At status06:42:34UTC, first control had added23210 physical hands in457.47 seconds
of controller time, including preparation/startup. Later raw metric iteration2223
reached10535125 cumulative physical hands,36891 above its retained10498234 parent.
These are progressing counters, not evidence of a stalled or missing process.

NVIDIA snapshots showed GPU utilization91-98%, used memory11196MiB of12282MiB;
one snapshot had graphics clock2775MHz, memory10251MHz,186.54W and71C. Windows
reported79.06GiB free of127.84GiB host RAM. The per-process GPU engine snapshot
also showed another PID55576 using56% of the3D engine, plus separate video-encode
activity. This is evidence of concurrent GPU use, not a controlled causal
attribution or additive utilization accounting. No unrelated app content was read.

The trainer's hands_per_second field was109.79 in that last row, but source line
9696 defines it as iteration trainable hands / collect_time: it excludes update,
checkpoint and other wall time and is NOT end-to-end physical hands/s. Do not
compare that field directly with the previous study's339.845 end-to-end training
physical hands/s or promise paper-scale completion from it.

The previous batch16384 memory qualification measured3.46GB peak allocated and
4.48GB reserved under its then-current workload, not guaranteed free memory under
today's other GPU activity. No memory exception has been observed in this run.
Keep fixed hand-dose comparison, record actual cell wall times and unknown shared
load, and do not call between-cell throughput differences an isolated gradient-
route performance benchmark. The registered7200s per-cell safe boundary remains
unchanged; if reached below target, preserve state and review remaining dose.

Read-only commands from repository root:

    nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader
    nvidia-smi --query-gpu=utilization.gpu,utilization.memory,clocks.current.sm,clocks.current.memory,power.draw,temperature.gpu --format=csv,noheader
    Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine | Where-Object { $_.UtilizationPercentage -gt 0 } | Sort-Object UtilizationPercentage -Descending | Select-Object -First 6 Name,UtilizationPercentage | ConvertTo-Json -Depth 2

No new training/evaluation hands were requested by this observation. The active
trainer continues to own and update its actual hand accounting independently.
