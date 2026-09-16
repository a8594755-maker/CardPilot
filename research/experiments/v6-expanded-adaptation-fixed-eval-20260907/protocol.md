# Fixed expanded-family adaptation diagnostic

Evaluate only all four final1M endpoints of the completed expanded-family trial.
Control comparator for both arms is each seed's original unexpanded parent in
the preceding execution-mixture trial, not the metadata-expanded derivation.
No training, checkpoint selection, retries or Slumbot hands.

Order: Seed1 control, Seed1 expanded, Seed3 control, Seed3 expanded.
Each job uses Standard10 then moving_s1, moving_s3, half_lr_s1, half_lr_s3
from the retained panel qualification. These four siblings were used to train
expanded policies: this is in-distribution adaptation, NOT unseen transfer.
Greedy physical200bb legacy_v4 observation contract remains unchanged.
1024 paired decks per anchor, both seats, parent and endpoint:20480 executions
per job,81920 total;10240 distinct planned decks shared between matched arms.
Deck seed20266401+10*training_seed, evaluator anchor offset1000003.
Preflight binds hashes and checks no overlap with retained raw evaluation corpus.

Primary contrasts: expanded minus control and each endpoint minus original parent
on four siblings, reported per training seed, both seats, and both ancestry
families. Standard10 is a separate preservation anchor. Fixed stratified paired
normal95 intervals condition on these policies/decks, not a seed population.
No outcome-triggered stopping or extra samples. Independent terminal raw review
must pass before interpretation or closing the record.

Decision: consistent sibling gains with retained-panel losses support a
distribution tradeoff hypothesis, not its causal proof; absent sibling gains
weakens that explanation and prioritizes learning-objective diagnosis.
Do not automatically scale or externally qualify any endpoint from this test.
