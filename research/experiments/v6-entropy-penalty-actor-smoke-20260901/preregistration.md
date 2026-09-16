# Matched entropy-penalty actor-head smoke

The same frozen actor scored -79.2126 bb/100 strict sampled but -9.4188 generic
greedy on separate fresh5k cohorts, a +69.7938 point shift.  Its 132,553-hand
training used entropy bonus +0.005/floor0.05 and produced slightly higher entropy
than Standard10 on preserved Slumbot states (0.52735 versus 0.51243).  Test
whether symmetric entropy pressure improves greedy learned-policy margins.

Train one treatment from exact legacy Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428
with the exact raw-parent configuration, seed20261042, worker seed2026104200,
fixed deal stream, five-anchor adaptive league, sampled hero, selfplay0.25,
all-policy-heads-only, lr3e-5, PPO2, target-KL0.01, advantage clip3, source
KL0.01, critic_v2 and fresh optimizer/counter.  The sole learning change is
entropy coefficient -0.005 and entropy floor0, making actor loss add
0.005*entropy.  Run at least131,072 physical hands.  Keep actor EMA0.9 only to
match parent instrumentation; evaluate the raw terminal model, not its EMA.

Freeze treatment plus the prior raw control and v6-rebound source.  Evaluate all
three in generic greedy mode against the same five untouched anchors with2,048
mirrored pairs per cell, common seed20261046 (61,440 hands).  Also replay the
treatment on the previously audited15,056 Slumbot decision states offline;
outcomes are not labels.  Require exact accounting, optimizer/frozen scope,
session audit, captured sources, and independent raw-pair aggregation.

Admit a separate262,144-hand entropy-penalty pilot only if the per-deck
five-anchor-average treatment-minus-control point is positive,
treatment-minus-source is positive, at least3/5 treatment-control anchor points
are positive, preserved-state treatment entropy is at least0.03 below control,
and treatment-control state-distribution TV is below0.10.  No Slumbot hands are
authorized in this experiment; internal admission does not prove strength.
