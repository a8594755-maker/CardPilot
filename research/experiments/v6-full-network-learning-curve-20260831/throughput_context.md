# Outcome-blind scalability context

This is a read-only analysis of the first12completed updates, not a change to
the current preregistered experiment. No new hands or GPU workload are generated.

The original AlphaHoldem paper reports eight TITAN V GPUs and64CPU cores, with
eight MPI threads each managing128environments and128steps. Its stated total is
6.5billion samples (about2.7billion hands); mini-batches are2048per GPU,16384total.
These are paper settings,not evidence that this host has equivalent throughput.
Source: [AAAI paper, Experimental Evaluations](https://cdn.aaai.org/ojs/20394/20394-13-24407-1-2-20220628.pdf).

Our current run uses one RTX4070 and12single-environment workers. Compute actual
completed hands from the persisted physical counter,not the legacy marker count
or transition count. Compare the logged collection and PPO times separately.
The console timings are rounded to0.1second; their sum omits startup,checkpoint
IO and other overhead. Any extrapolation from these12updates is a conditional
lower-overhead estimate,not a measured future rate or commitment to2.7B.

If corrected-contract learning proves useful, separately profile the already
implemented multi-environment worker path and batch scheduling before substantial
scaling. First require real rollout parity/accounting tests beyond constructor
wiring. Do not modify this live run,assume its training reward proves strength,
increase the fixed budget,or enable legacy ELO/replay paths without v6 validation.
