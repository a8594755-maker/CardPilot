# Independent observable critic qualification decision

Qualified for a bounded matched learning experiment, not for promotion or scale.
The original network/worker observation and action contracts are unchanged. The
only new learned path is a separate GroupNorm card/action/stack/fusion encoder
feeding the existing public value head. The actor cannot receive value gradients.
All current default global clipping behavior is retained, so the expanded critic
can still affect shared clip magnitude: this is not guaranteed actor-update parity.

Evidence: 16 encoder/actual-forward/disk-Adam tests, six resume-boundary tests,
both original fixed2M parent retained-state checks and actual PPO fixtures; real
seed1 first derivation, seed1 extended resume and seed3 captured first derivation.
Three completed runs collectively executed 18,158 new physical hands, 16,474
transition-bearing hands and 30,987 replay rows. No strength-evaluation or Slumbot
hands. Real-worker reviews demonstrate new encoder updates, original optimizer
step continuity, source/parent hashes and append-only evidence prefixes.

The seed1 extended restart preserved and independently reopened initial_resume.pt:
all 162 Adam states, model, replay content/RNG/counters, pool and assignment origin
equaled the parent, with a new managed namespace. Seed3's initial architecture
derivation independently preserved all original weights and Adam moments and
cloned exactly 76 encoder parameters; new moments were initially absent and
created by training. These are statistical resumes, not bitwise worker equivalence.

Deviations preserved: first seed1 initial save was overwritten normally and is
not retrospective initial-state proof; the captured restart supplies its own
evidence. First seed3 attempt stopped before workers/new hands because a reviewer
constructed dict versus OrderedDict and strict equality rejected the container
type. A separately retained v2 checker fixed that only; new directory and attempt
namespace were used, no failed attempt removed. The initial first-run reviewer
assumed four Adam updates instead of deriving eight from fresh-plus-replay rows;
it was corrected without changing training evidence.

Next: preregister one two-seed control/treatment family from the ORIGINAL fixed2M
parents, not these smoke descendants. Doses +262144 and +1048576 actual physical
hands per arm; preserve controls and full optimizer/replay continuity. Freeze
commands, hashes, fresh paired evaluation seeds and heterogeneous opponent panels
before training. Replicated two-seat improvement and preservation—not critic loss
or small-test wins—determine further compute. No automatic 4M or Slumbot allocation.

Production wrapper must retain the captured-initial evidence path appropriate to
first derivation versus extended resume. All source files used by completed
qualification attempts remain immutable; new production wiring belongs in its
own experiment. Do not describe this qualification as a stronger poker model.
