# Conditional phase1 learned average update

Prepare while the original v6-average-response-oracle-pilot-20260831 trains.
This record stays PLANNED. Do not run any new hand or GPU work until that exact
parent finishes COMPLETED with independent PASS/ADMIT_SEPARATE_AVERAGE_UPDATE.
Freeze its reviewed_analysis SHA256 and exact final checkpoint SHA256 in the
launcher after completion. Unknown/missing digests fail before output creation.
No internal checkpoint selection: use only the parent's preregistered final.

The two immutable teachers are the prior average (cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b)
and that final learned PPO response. Update the NORMAL-FORM average with weights
1/2 and1/2: for each physical hand and each seat independently, choose a teacher
uniformly and keep its identity fixed for the whole hand. Learn the conditional
behavior from its visited states and soft legal-action probabilities. This is
not a parameter average or an unweighted per-state probability average. The
whole-episode sampling accounts for each teacher's own reach probability; the
finite, truncated policy representation still prevents claiming exact realization
equivalence or perfect recall. The previous average is one warm-start prior,
not17new best responses and not18equal fictitious-play iterates.

Reference: Heinrich and Silver2016,section2.3 equation1 andsection3:
https://arxiv.org/html/1603.01121v2. This is a phase of approximate fictitious
self-play using an on-policy PPO response oracle, NOT the paper's complete
anticipatory off-policy DQN NFSP algorithm and not a Nash guarantee.

Collect exactly262144NEW native200bb training-data hands from this two-policy
whole-hand mixture, and8192separate supervised-validation hands. Both seats use
the mixture. Frozen teachers on GPUfloat32, canonical float64 legal softmax,
temperature1. Seed2026101501training,2026101502validation,2026101503reservoir,
2026101504fit. Full52-card decks and independent physical-seat action-uniform
streams. Uniform Algorithm-R decision reservoir262144rows, serialized with RNG,
seen count, observation tensors, targets and exact raw row identities. Do not
reuse/reset/overwrite the previous reservoir, hands, optimizer or teacher files.

Reuse the already qualified temporal_average collector as an unchanged local
copy, with2teachers instead of17. Preserve full raw deck/action/probability/target
hash chains. Audit every trace and retained reservoir row; scalar-replay the
first64production hands as the fixed GPU/scalar rounding diagnostic. Beforehand,
compare both teachers on64preserved public states in scalarCPU,batchCPU,batchGPU
with maximum absolute probability error2e-5. These replays add0new unique hands.

Initialize the new average from the prior average weights only. Train shared
representation and both policy heads (80parameter tensors), freeze6value-head
tensors. Fresh Adam1e-4,batch1024,gradientclip1,exactly4complete reservoir epochs
(1024steps); only fixed epoch4 is the result. This shorter preselected SL schedule
is motivated by the previous12-epoch experiment's falling training CE but rising
late validation CE, not by this new experiment's outcomes. Record epoch1/4heldout
losses diagnostically; do not select an earlier epoch or extend on partial scores.
No reward-gradient training in THIS record; the parent's new PPO hands stay in
the parent accounting and are not counted again. Checkpoint metadata explicitly
identifies an SL-only algorithm/optimizer and cannot masquerade as PPO resume.

After full collection/fit evidence checks, independently recompute heldout
cross-entropy improvement over the prior average with hand-cluster95%CI.
Its lower bound>0 admits a SEPARATE frozen average assessment and subsequent
response phase; it is a behavior-fitting gate, not a strength or Slumbot gate.
No external hands or100k admission in this record. No automatic retries/restarts;
preserve partial evidence and account preserved complete raw hand claims on failure.
The unchanged collector commits at1024-hand barriers. If interrupted mid-barrier,
additional terminal hands may exist only in RAM (at most1024); mark that count
unknown instead of falsely claiming an exact total or automatically replaying it.
No lossless collector resume is claimed. Successful completion requires exact
full-budget raw evidence and the complete audit.
Finish this same record for a valid positive OR negative fitting result.

Capture all code/patch/source copies, exact commands, dependency and model SHA256s,
wall time, live physical counts and independent terminal review. Leave the active
parent and all its frozen code/checkpoints/hand evidence unchanged.

Exact launch after parent admission digests are frozen:
python research/experiments/v6-fictitious-average-phase1-20260831/run_distillation.py

Exact independent terminal review:
python research/experiments/v6-fictitious-average-phase1-20260831/review_finish.py
