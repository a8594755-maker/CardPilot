# Execution-contract findings and correction of interpretation

The five fixed probes in audit_analysis.json all found discrepancies using
unchanged production sources. The audit completed zero environment hands,
training hands or Slumbot hands and attempted zero network calls. All63 captured
source/copy pairs were unchanged. A separate read-only check verified the exact
five stored counterexamples and matched six relevant runtime files and copies
across each of these three experiments,18 historical source/copy pairs total:

- matched-weak-kl-representation-curve-20260830
- representation-scope-independent-confirmation-20260831
- representation-full-strict-sampled-slumbot20k-20260831

The six files were environment.py,environment_v55.py,game_state.py,
v5_mirror_eval.py,play_slumbot.py and train_v5.py. Exact source hashes and full
copies remain in the respective execution_code/copy_manifest.json snapshots.
Earlier experiments have not been exhaustively audited by this diagnostic.

| Probe | Native training / mirror behavior | Slumbot-side contract |
|---|---|---|
| Posted-blind action binding | Trainer slot7 raises to4bb; mirror slot7 raises to2bb and disables slots3..6 | Slot7 raises to4bb; slots3..7 offer2,2.34,2.5,3,4bb |
| First SB completion | Engine immediately advances to flop and deals3board cards | BB still has its preflop option; no board cards |
| Opening in a2bb flop pot | Native table permits0.66bb | Client table enforces at least1bb unless all-in |
| Raising a3bb opening bet | Native table offers raise-to5.64bb | Client table raises to at least6bb |
| First flop all-in | Native v4 history encodes the action asRAISE | Client v4 history encodes it asBET; two one-hot cells differ |

## Required correction of interpretation

The internal discovery and confirmation retain their observed raw outcomes and
mathematically computed intervals, but their description as the same deployed
native-sampled policy is not justified. Identical weights are insufficient when
the legal masks and slot-to-physical-action binding differ. The positive internal
intervals describe the legacy mirror execution in its native simulator, not
evidence that the exact Slumbot-executed policy became stronger. Do not reuse that
internal admission result to promote another run without a repaired contract.

The external20k result remains valid observed evidence for its actual frozen
strict sampled deployment: -81.251bb/100,95%CI[-123.160,-39.342], with8clean client
exits and passing raw/session audits. No hand, checkpoint, prior statistic or
primary analysis is changed by this addendum. The historical Standard10 and
heads-only external samples are unpaired; their point differences are not a
matched causal treatment estimate.

These five deterministic counterexamples establish interface/rule differences,
not their frequency in play or how much of the external loss they caused. The
previous zero-hand loader/forward test remains valid only for identical input
tensors; it explicitly did not validate encoders, game rules or action binding.

## Next research action

Prioritize a separately recorded rules/action/observation-contract repair with
independent poker-rule and chip-conservation tests. Preserve the legacy sources
and snapshots needed to reproduce these findings. Unify the configured physical
action binding used in training, internal evaluation and external deployment;
cover the BB option, minimum bets/raises and canonical all-in history encoding.
Only after those contracts pass should new corrected-environment training and
fresh internal evaluations be run. Do not pool repaired results with legacy
mirror results, extend the negative20k pilot or launch a100k qualification now.
