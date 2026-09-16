# Independent review attempt 2

The second independent review again recomputed the saved-array statistics, then
showed that a 64-state repeat linkage call does not use the same Transformer batch
shape as the production diagnostic's fixed 512-state inference batches. The GPU
linkage delta consequently exceeded 1e-4. This attempt made another 64 CPU and 64
GPU model-state queries and wrote no reviewed result. The next review replays the
first complete 512-state batch, preserving the original inference batch shape.
