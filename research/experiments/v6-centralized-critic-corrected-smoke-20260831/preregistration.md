# Corrected privileged centralized-critic matched smoke

The first CTDE smoke parent stopped after a complete67,014-hand control because
the newly returned centralized_critic and preupdate_critic_mse fields were not
copied into h1_training_metrics.jsonl. No treatment or evaluation started. The
parent remains FAILED and its control is not reused. The serializer is repaired
and tested before this fresh experiment.

Repeat the already-fixed CTDE architecture and gate with entirely new matched
training randomness: independently train control and treatment from the same
legacy Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428
for at least65,536 physical v6 hands each using seed20261041 and worker seed
2026104100, a common fixed deal stream, five frozen learned anchors, adaptive
league, sampled hero/selfplay0.25, lr3e-5, PPO2, target-KL0.01, advantage clip3,
source KL0.01, entropy0.005/floor0.05 and fresh optimizer/critic/counters.
Control updates four policy-head tensors plus six public-critic tensors;
treatment updates the same actor tensors plus six privileged-critic tensors.
No replay, continuation, EMA, sequence adapter, endpoint selection, parent
checkpoint reuse, or parent control reuse.

Require the two new metric fields in every iteration, finite values, exact
physical accounting, model/optimizer/frozen-source scope and PASS session audits.
Freeze both endpoints. Evaluate source/control/treatment against all five
untouched anchors using2,048 mirrored pairs per cell and common seed20261040
(15 cells/61,440 hands). Admit a262,144-hand CTDE pilot only if the per-deck
five-anchor-average treatment-control point exceeds-10bb/100, treatment-source
point is positive, at least3/5 treatment-control anchor points are positive,
the treatment final-half median pre-update critic MSE is below control, and all
evidence gates pass. Failure redirects to a matched EMA actor-target smoke.
Slumbot hands=0.
