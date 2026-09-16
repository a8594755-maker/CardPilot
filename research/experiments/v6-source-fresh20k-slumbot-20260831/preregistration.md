# Fixed fresh20k corrected-v6 source external baseline

The source has completed a separately recorded16hand live protocol probe with
63real API requests,47saved decisions exactly replayed,12folds and4showdowns,
both seats,disjoint token chains and no ambiguous requests. No all-in was observed
in that probe; broader live compatibility remains conditional on this full run.
Exclude all16probe hands from every statistic below.

## Fixed policy and budget

Source SHA256944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2,
copied without modification from v6-source-live-readiness-20260831/frozen/source.pt.
Same v6 contract,strict native sampled policy/temperature1,CPU1thread,200bb,
100chips/bb. Use the existing immutable journaled-client runtime snapshot from
that successful probe. No learned weight,metadata,rule,heuristic or action changes.

Exactly eight new sessions s01..s08,2500hands each,policy seeds2026092901..2026092908,
session IDs v6_source_fresh20k_20260831_s01..s08. All8launch once; at most8CPU clients,
no training. Six existing CPU internal league evaluators may continue unchanged.
Each client starts with no token and uses only slumbot.com new_hand/act APIs via
the verified-TLS no-retry persistent transport. No real-money wager or login.

Fixed20,000fresh hands; no interim score checks,early success stop,alternate seed,
extension,resume,overwrite,failed-hand replacement or pooling. Every client fails
closed on any transport/protocol/policy/evidence error. Other already-launched
sessions may finish their original budgets; no new session replaces a failure.
Any incomplete/invalid session makes this baseline invalid for strength admission,
with all evidence/actual raw counts preserved. Do not retry an ambiguous request.

## Evidence and statistics

Before requests: verify completed live-readiness record,its frozen model/runtime
copy hashes,zero-hand snapshot loader evidence,all77unchanged source copies and
three frozen identities of the ongoing league matrix. Capture this record's
SHA/patch/helpers and exact expanded commands. Test fixed-budget/orchestration
statistics. Preserve fsynced intent/response/hand journals and all child exits.
Update evaluation_hands/slumbot_hands from complete durable raw rows while running;
report attempted hands,server terminal claims and unresolved requests separately
if any failure prevents full validation. Validity is not inferred from counters.

After all clients exit: independently audit each complete journal,terminal chip
arithmetic,server session counts/totals,all sampled model decisions,exact frozen
checkpoint/runtime,contiguous hand indexes,and disjoint complete token chains.
Distinct IDs,seeds and token chains do not prove independence of server RNG.

Only if all20,000hands and all audits pass,derive results from raw winnings_chips.
bb/100 is mean(winnings_chips),since a BB is100chips. Primary95% interval is
mean +/-1.96*sample_std(chips)/sqrt(20000). Also report the equal-session mean
and95% t7 interval using the8session bb/100 means and t0.975,7=2.3646242510102993.
The latter is a session-cluster sensitivity check,not proof of server independence.
No old baseline subtraction,milestone tags,probe pooling,or internal-hand pooling.
Historical greedy/sampled old-contract baselines are context only,not matched arms.

A point estimate>0 with BOTH95% lower bounds>0 may support a separately
preregistered fresh100k confirmation of this exact unchanged source policy.
It is not the100k Goal and launches no automatic extension. Otherwise the source
baseline supplies external calibration,not a candidate-promotion loophole. Existing
league and source-KL candidate gates are unchanged. No other frozen policy may be
selected from these results. New environment training hands=0.
