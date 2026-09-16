# Fixed temporal aggregation outcome

All98304 internal executions completed in2114.641 seconds with normal exit0.
Independent raw review recovered16384 unique mirrored decks,0 overlap against
1148930 inventoried prior rows, and unchanged source/checkpoint hashes. This
is not a final Slumbot qualification and does not demonstrate unseen generality.

Equal probability aggregate minus final iterate, pooled bb/100:
- Seed1: -1.2216, conditional95CI[-10.0621,7.6189].
- Seed3: +8.2383, conditional95CI[-0.5995,17.0761].

Aggregate minus own root:
- Seed1: +2.1733, CI[-4.7910,9.1377].
- Seed3: +0.5234, CI[-10.3051,11.3519].

Final iterate minus own root: Seed1+3.3949[-7.4512,14.2410];
Seed3-7.7148[-19.8284,4.3987]. Aggregate Seed3 preservation-minus-root
is-5.7952 with CI spanning zero; Seed1 aggregate-minus-final panel means are
both negative. Thus the preregistered external calibration gate is false.
These are conditional unadjusted CIs, not equivalence or impossibility results.
There is no replicated gain and no proof of policy cycling or stable improvement.

Total execution costs (engine and opponent inference included):root513.568s,
final510.073s,aggregate1061.308s. Their total decisions are197311,196356,197113.
The aggregate costs about2.08x final at similar decision counts, with no proven
benefit. This is not a pure neural-inference latency benchmark.

Decision: do not promote this aggregate or open a checkpoint/weight sweep; retain
all policies and raw evidence. No automatic external test or larger ensemble.
Return compute allocation to learned-weight training. Before another long run,
use existing realized-update evidence to choose between a longer fixed-regimen
continuation and an actor-objective revision; avoid repeating completed audits
or mistaking a deployment ensemble for a stronger learning algorithm. A negative
or inconclusive deployment-ensemble result does not rule out longer training.
