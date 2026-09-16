# Real-worker v6 single/multi rollout contract diagnostic

Outcome-independent CPU-only validation while the separate source-KL pilot trains.
No production source, frozen checkpoint, optimizer or running session is changed.
No neural-network inference, GPU operation, optimization or external call occurs.

Fixed9cases: worker single/M1,multi/M1,multi/M4 crossed with passive_self,
allin_self,fold_anchor. One real spawned worker per case uses the actual v6
environment and production worker function,real named shared memory and pipes,
fixed seed2026092200 and deck stream. The controller supplies deterministic fixture
actions with log-probability/value0,not a learned or deployable policy. Stop after
at least64physical completed hands,report any asynchronous overshoot. Each case
has a60second operational bound and only its own worker may be stopped on failure.

Instrument the environment ONLY inside the diagnostic child process to emit
terminal/deck/action events; preserve production source byte-for-byte. Independently
replay each actually completed event through the unmodified native environment
in the controller to check each consumed shared-memory observation,model request,
return,chips committed and expected transition block. Compare exact contiguous
hand blocks and physical/zero-decision counters; compare common M1 single/multi
deals. This is a data-flow/serialization check,NOT an independent rules oracle:
the earlier PokerKit audit remains the separate rules evidence.

Retain request streams,terminal events,transition packets,process exits,source
copies/hashes/dirty patch and per-case analyses. Reference replay hands and worker
validation hands are separate metrics; both are EXCLUDED from new_training_hands,
evaluation_hands and Slumbot counts. Reused fixed deals are intentional,not new
independent performance evidence. A passing diagnostic does not validate real GPU
inference batching,PPO scaling,assignment switching,arbitrary policies or multi-slot
checkpoint/resume semantics. Those remain separate follow-up gates before scale-up.

Exact first command:
python research/experiments/v6-multi-rollout-contract-audit-20260831/run_audit.py

The default output is attempt01 and is never overwritten. Any diagnostic-harness
repair requires explicit review,new source provenance and a new numbered attempt;
no automatic retries or mutation of the active learned-weight experiment.
