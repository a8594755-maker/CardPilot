# Managed resume integrated and GPU-qualified

The exact staged trainer SHA2561b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b was integrated into production only after the 4M evaluation owners/children were terminal and its existing record was completed. Full AlphaHoldem plus logger regressions passed379/379; py_compile passed. Earlier CPU evidence was retained, not rerun:600 retained complete-update physical hands and100 deliberately interrupted/discarded exposures.

## Real current-recipe GPU evidence

All four preregistered ABBA attempts completed at full update boundaries, each with two new updates and a distinct durable namespace. First attempts forked the exact original Seed1 4M SHA7ea4d74d; second attempts resumed their own arm's checkpoint without counter or optimizer reset. Every first-attempt and resumed-attempt gate passed, including exact initial weights, optimizer/LR, replay entries/RNG/draw count, league snapshots/metadata/history, iteration and both counters. Updates and replay draws advanced with finite metrics. The second attempts restored Python/NumPy/Torch CPU and CUDA RNG exactly at the saved initial boundary. Legacy first-parent RNG bootstrap is explicitly declared; worker action RNG and in-flight rollout continuity are statistical, not bitwise.

| Arm / attempt | New physical executions | Transition-bearing hands | Subprocess wall seconds | Physical hands / wall second |
|---|---:|---:|---:|---:|
| single1 /1 | 9,880 | 8,265 | 112.719 | 87.652 |
| multi8 /1 | 9,756 | 8,195 | 60.645 | 160.872 |
| multi8 /2 | 9,990 | 8,271 | 60.783 | 164.355 |
| single1 /2 | 10,106 | 8,216 | 117.850 | 85.753 |

GPU totals:39,732 physical executions,32,947 transition-bearing hands,8 new updates. Manifests separately identify5,815 physical hands with no trainable decision. The residual physical-minus-transition-minus-no-decision gap is970 (294/239/165/272 by ordered attempt), consistent with the declared inclusion of unconsumed worker tails; it is not counted as extra training samples. Do not call every completed environment hand a consumed transition. CPU plus GPU diagnostic executions total40,432; no diagnostic checkpoint is promoted and no copied prefix is counted again. Research-lineage hands, internal strength-evaluation hands and Slumbot hands remain zero in this infrastructure experiment.

Parent/model/prefix/source hashes remained unchanged throughout execution. All12 observed workers per attempt exited naturally; the controller completed with exit0 and the OS subsequently showed no GPU qualification/trainer process. The original stopped-v1 guard remains unchanged; the terminal-v2 handoff qualified352 frozen inputs. Qualification input maps are in gpu_current_recipe_v1/input_contract.json and every attempt retains exact argv, process identity, wall time, raw prefixes/suffixes, initial/final checkpoint, receipt and verification.

## Decision and limitations

Pooled subprocess-wall throughput is86.681 physical hands/s for single1 and162.615 for multi8:1.876x. Both first/resumed ratios pass (1.835x/1.917x), so multi8 passes the preregistered provisional throughput criterion. Complete runner time, including controller verification overhead, was438.558s. This is a short, ordered, single-parent diagnostic, not a long-run throughput estimate, causal performance interval or poker-strength result. Within-attempt rates (~649-658 physical hands/s for multi8) omit startup/cleanup and must not replace the primary cost measurement or justify an unsupported paper-scale timetable.

Production managed resume is qualified for subsequent controlled use. Prefer multi8 for the next authorized training allocation, with a fresh receipt per launch and realized cost monitoring. Preserve optimizer/replay and label statistical worker continuation. Do not retroactively repair Seed2's old repeated exposures, reuse namespaces, reset counters or promote diagnostic descendants. The next scientific measurement is the fixed original Seed1 4M external development calibration, separately preregistered; unchanged three-seed8M remains unauthorized.

After the GPU runner had completed, a prose-only correction in the 4M summary changed its drift comparator from an erroneous2M label to the actual frozen Standard10 parent. Exact original4M summary and record snapshots are retained here, byte-identical, as qualified_4m_result_summary.md and qualified_4m_experiment.json; the GPU input contract's original record SHA remains recoverable. No original numeric evaluation evidence or GPU result was changed.
