# Conditional fixed phase2 average fresh100k qualification

Prepared while the exact epoch08 fresh20k pilot is still RUNNING, without reading
interim returns. This is a separate prospective qualification, not a pilot
extension. No network, learned-model queries or unique hands in preparation.

Only candidate:
c60dfc881ff1b97245219b226eabb5f4c00c1a3d421f71681b63097f45bfa3ea.
Same fixed epoch08 policy, unchanged qualified CPU float32 sampled-temperature1
runtime, no action overrides/adaptation or model replacement.

## Admission
Parent v6-fictitious-average-phase2-fresh20k-slumbot-20260831 must first finish
all8x2500hands and independently pass complete journal/decision/terminal/session/
server-counter/token evidence audit. Require COMPLETED/PASS,
ADMIT_SEPARATE_FRESH100K_CONFIRMATION, exactsamefrozenmodel and pilotpoint>0.
Pilot CI may cross zero; positive pilotpoint is allocation, not significance.
The complete reviewed pilot digest must be frozen before qualification can start.
No current pilot scores or provisional survival subsets may admit this run.
Nonpositive/invalid parent -> do not launch; close conditional plan STOPPED.

## Fixed protocol
Exactly100000NEW Slumbot hands,8new sessions of12500, maximum8clients.
Seeds2026102301..2026102308.
IDs v6_fictitious_average_phase2_fresh100k_20260831_s01..s08.
Freeze all commands,model/runtime/source/patch identities before the first request.
No retries/replacements, hidden partial-data discard, early score stopping, budget
extension or extra candidate. All8original fixed budgets finish normally unless
a client itself encounters an unrecoverable infrastructure failure; preserve it.
Never restart a missing session or silently replace observed/ambiguous hands.

Use the qualified journaledclient/auditor, unchanged durable intent/response/
commit/raw protocol and full final model/seededuniform replay. Require eight
complete sessions,allclients+auditor normalexit, exactmodelhash, allruntimehashes,
terminalpayoff and server handindex/cumulativecounter reconciliation. Token
chains must be disjoint among all8and all SEVEN prior corrected-v6 live audits,
including this candidate's fresh20kpilot. Distincttokens do not prove server RNG
independence. Oldsix audit identities remain pinned, and pilot audit is added
only after reviewed completion. No v5baseline or milestone adjustment.

## Single fixed analysis
Read raw outcomes only after all100000hands complete and evidence audit passes.
100chips=1bb; mean chips/hand numerically equals bb/100.
Primary raw-hand normal95%CI; additionally report eight-session t7 95%CI.
Only mean>0 AND rawlower>0 AND sessionlower>0 permits a conservative Goal claim,
and ONLY after independent full-scope evidence/arithmetic review. The pure stats
helper always leaves goal_achieved=false because numerical results alone do not
prove provenance, frozen identity or freshhand validity.
CI assumptions (independent hands or independent session clusters) are explicit;
no proof of server RNG independence or universal opponent strength is claimed.

Zero pilot/probe/internal/validation/oldcontract hands pooled. Thisrecord alone
must contain100000fresh hands from one unchanged policy. Failure/inconclusive
statistical results end the fixed record; no optional extension or replacement.
A valid negative/inconclusive result is COMPLETED scientifically, not FAILED.
Then independently choose a new research experiment; do not redefine Goal.

## Implementation status
PLANNED ONLY. Fixed statistic/admission contract and offline tests are prepared.
No qualification launcher,execution,session or checkpoint copy exists yet.
Only if parentpositive and independentlyreviewed: implement and verify the
fixed-budget launcher using the qualified pilot evidence machinery, freeze the
parentreviewhash, register exactexpanded commands and capturecode before launch.
Any implementation must satisfy this preregistration without changing outcome
rules after seeing the parent. Preparation fixtures generate0physicalhands.

Preparation:
python -m pytest research/experiments/v6-fictitious-average-phase2-fresh100k-qualification-20260831/test_qualification.py -q --junitxml=research/experiments/v6-fictitious-average-phase2-fresh100k-qualification-20260831/preparation_tests.xml

