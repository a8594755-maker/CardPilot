# Journaled v6 external-client offline readiness

Register before implementation/testing. The active source-KL pilot continues
unchanged; only NEW modules are added outside its71captured source paths.
Integrate the validated terminal component with strict CPU sampled inference,
one-request persistent transport and durable append-only request evidence.
No poker API,authentication,training update or policy-strength evaluation occurs.

Before each state-changing request, flush/fsync an intent containing a sequential
request ID,hand attempt,input-token hash,and full sampled decision context. Before
using a response, persist its public game fields and returned/effective token
hashes. Never persist plaintext tokens or raw exception messages. Retain failed
and partial hands; no automatic retry,resume,new session,drop or replacement.
Use hash-linked canonical JSONL events and exclusive output creation. A partial
write or abrupt exit is incomplete evidence,never a successful zero-hand result.

Accept completed hands only after exact terminal validation,request continuity,
and server session hand-count/total consistency. Preserve raw per-hand outcomes
and their journal commit references. A successful session also requires final
frozen checkpoint/runtime identity checks,exact hand budget and a closing event.
The policy remains the shared v6 CPUfloat32/float64 legal-softmax sampled policy,
temperature1; the journal must neither draw extra policy RNG nor alter actions.

Implement an independent state-machine auditor for journal ordering/hash chain,
intent/response token transitions,committed-hand arithmetic,final summary,
partial/failed requests,and seed/ID/token disjointness across sessions. Replay
persisted decisions through shared inference with the original uniform variate;
verify that the sequence comes from the declared policy seed. Reject tampering,
duplicated/mixed streams,unknown completion and semantic changes even if an
attacker rehashes JSON. These checks do not prove server RNG independence.

Offline fixed coverage includes normal two-hand sessions,opponent-fold with no
decision,midhand/interhand token rotation,omitted unchanged token,missing/invalid
initial token,first/second new-hand and act failures,invalid reward/type/bounds,
premature terminal,missing showdown cards,changed cards/history/seat,server error,
server counters/totals mismatch,policy failure,checkpoint/source identity change,
intent/response persistence failures,abrupt child exit after durable intent,
raw/journal/summary tampering,duplicate IDs,seeds and token chains. Retain every
attempt's fixtures/logs/manifests and failure evidence; no overwritten attempts.

Also check real frozen v6 source-model inference on a small fixed offline session
to establish that wrapping does not alter shared sampled decisions. This is
execution validation,not policy selection or strength evidence. Use no GPU.

Every new training/evaluation/Slumbot hand count remains0. Report synthetic
fixture trajectories,decision replays and test counts separately. Snapshot exact
sources/hashes/patch and verify the live pilot's71source pairs before/after.
Passing grants OFFLINE_CLIENT_EVIDENCE_READINESS only,not live compatibility or
100k qualification. Any later live use needs its own frozen-policy preregistration,
transport/process supervision,session audit and outcome-independent abort rule.

Exact first command:
python research/experiments/v6-journaled-client-readiness-20260831/run_readiness.py --attempt attempt01
