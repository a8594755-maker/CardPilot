# Same-experiment interruption recovery

This amendment preserves the original protocol, trainer, completed stages and
interrupted `static_stage2` directory. It does not start a new research experiment.
The original controller and trainer were independently observed absent, with no
terminal receipt. Cause, exit code and uncheckpointed worker suffix are unknown.

Resume only from the retained iteration1525 checkpoint SHA256
`c44a52bcbcc30e88c8e6a96a0d6d6c0eb1a869d5041585129e942d3a8a587974`:
7,237,515 physical hands, 6,284,575 transition-bearing hands. Target stays
8,392,280 physical hands, leaving1,154,765 plus completed-update overshoot.
Preserve optimizer/LR, replay entries/RNG/count, pool and assignment history.
The intact pending assignment for iteration1526 must be replayed verbatim;
it is not a completed update or grounds to trim the original prefix.

A new durable namespace prevents reusing any prior attempt's deterministic deal
identities, including the unknown crash suffix. This is statistical worker
continuation, not bitwise continuation or proof that all executed hands survived.
Unknown suffix hands remain null/unknown, never zero or credited to the target.
No original files are overwritten. New status/ownership/training artifacts live
here; original stage2 evaluation output paths remain unused until evaluated.

Use `resume_control.py --audit-only` once to capture the interruption and validate
retained state, full assignment replay, raw prefixes and source hashes. Tests and
the audit must pass before `resume_control.py --run`. Launch the controller as a
hidden background process with file-backed output, independently of an observer
PTY. PID plus creation time, not a RUNNING label, establishes liveness.

The controller reuses the frozen original evaluator and completion verifiers;
only static-stage2's endpoint path is redirected to this new attempt. Both final
endpoints get the original fixed seed20263412 evaluation and seed20263422 drift
audit. No new Slumbot hands, algorithm branch or automatic retry is introduced.
The controller stops for researcher analysis after these planned evaluations.
Unexpected observer errors drain an already-started bounded trainer and prohibit
subsequent jobs; tests cover this control boundary, not arbitrary OS termination.
Retained-prefix, recovery-attempt and whole-stage accounting remain separate.
