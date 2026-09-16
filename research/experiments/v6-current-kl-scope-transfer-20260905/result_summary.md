# Scope-transfer prerequisite qualified; no strength claim

The fixed two-parent qualification passed25 unit tests and actual serialized
checkpoint/Adam checks. It added zero environment training,evaluation or Slumbot
hands. Original checkpoints and production trainer/network were not modified.

Both parents retain their original learned weights and all138 other checkpoint
fields recursively,including physical/transition counters,iteration,replay
entries/replay RNG/cumulative rows,pool/assignment origin and main-process RNG.
Earlier lineage interruption/freshness limitations remain unchanged.

| Parent | Retained physical hands | Retained iteration | Existing Adam step | Disposable fixture next step |
|---|---:|---:|---:|---:|
| Seed1 static | 8395752 | 1768 | 7070 | 7071 |
| Seed3 static | 8392377 | 1773 | 7090 | 7091 |

The producer-verified10 head/critic parameter IDs0..9 map by name to full-network
IDs76..85. All original moments,step tensors and group hyperparameters are
preserved. The full group contains86 parameter IDs,but only the original10
states before any update. The76 previously frozen representation tensors get
state only on their first gradient; their Adam clock is1,not fabricated history.
The effective LR remains9.999999999999996e-05 after loading,even though the
optimizer constructor used CLI-like.0003. There was no optimizer reset.

Actual PyTorch Adam loading and one supplied-gradient fixture per seed verified
bitwise-identical updated head parameters AND Adam states versus heads-only
controls. Full-model body tensors changed and acquired first-step states; control
body tensors did not change. These disposable updated models were not persisted.
This proves transfer/update mechanics under the same supplied gradients,NOT
equivalence of full-backprop PPO gradients,rollout RNG continuation or strength.

Exclusive,unstepped derived checkpoint copies preserve original weights:

- `derived/seed1_full.pt`: SHA256
  `44d332a0e234b7806933680417095d6d2bcc0daf2779119d5b72bb36ca8c589f`.
- `derived/seed3_full.pt`: SHA256
  `12ac34ea420a6907add175c50e862d8a8f3b1f6e179c80bba9eb9eea60e55d9a`.

Only optimizer ID mapping,the all-policy-heads-only flag,and an explicit scope
transfer provenance field differ. Existing whole-file parents remain unchanged.
The actual-parent qualification took12.766seconds;25 tests took5.461seconds.
Experiment lifetime includes inspection/implementation and is not training time.

Independent inspection of the code and recorded outputs confirms that names are
derived from the exact producer's ordered parameters and the actual original
single-group Adam scope,not guessed from shapes alone. Tests reject duplicate/
missing IDs,state shape/dtype/nonfinite errors,changed replay/RNG/counters and
output overwrite. Complete state roundtrip was checked on both real artifacts.

Next: separately preregister the matched current-regimen representation-learning
versus heads-only pilot from BOTH static8M parents. Keep the same existing-policy
state,static Standard10 KL reference and environment/observation/action contract.
External reference inputs are runtime/command bindings and still require checking
in that pilot; preserving checkpoint metadata alone does not certify them.
Use fresh managed attempt namespaces and actual initial model/optimizer/replay/
counter/RNG audits. Do not reuse the retained old attempt namespace. Qualification
does not certify the full production launch,CUDA update equivalence or unknown
historical worker tails. Preserve the same reference input and learning rate and
do not quietly add an extra optimizer group or reset any state.

This is a prerequisite for genuine new learned-weight training,not a new
profitable policy,automatic16M authorization or final100k qualification.
The larger pilot must use geometric multi-seed,both-seat,heterogeneous evidence;
small negative absolute results alone do not reject long-run learning.

Actual qualification report SHA256:
`c35191054e22401c207f3384b851b7c9f5c790500cf8ebdaead12dd0dadebd92`.
