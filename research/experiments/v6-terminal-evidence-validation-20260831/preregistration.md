# Offline terminal-evidence validation

Registered before implementation or testing. This addresses the terminal-bound
and premature-terminal findings of v6-external-evidence-protocol-audit-20260831.
It adds a standalone module; it does NOT edit any captured source of the live
v6-source-kl-retention-pilot-20260831, change policy inference, integrate a client,
contact a poker API, or authorize an external benchmark.

Hypothesis: explicit integer-chip terminal replay can reject malformed outcomes
while accepting legitimate folds, showdowns, and all-in runouts. Require exact
200bb stacks, integer reward within +/-20000 chips, valid distinct known cards,
legal physical history, consistent board length, terminal status, exact fold
payoff, and exact showdown payoff when opponent cards are disclosed. Showdowns
without opponent cards fail closed (no guessed cards for payoff validation).
Optionally validate the previous live response and sent action against the final
response, including unchanged own cards/seat and monotonically extended board.

Use the primary API sample at https://slumbot.com/sample_api.py for wire syntax,
including all-in suffixes such as b20000c/// and per-street bet amounts. Preserve
the retrieved file and its hash; do not execute its network or main functions.
Public documentation GET is not a poker request. Do not contact any poker API.

Directed unit cases cover folds in both seats, no-decision opponent folds,
ordinary showdown/tie, preflop/flop/turn/river all-ins with supported suffixes,
short all-ins, malformed action separators, bounds/types/cards/history, missing
showdown cards, altered payoffs, and response continuity. Reject bad evidence;
never repair a reward, drop a losing hand, retry, or select a replacement.

Additionally use exactly512 fresh fixed synthetic decks with seed20260922 and
the pinned previously validated PokerKit0.7.5 oracle adapter. Compare each native
action and final payoff to that independent rules implementation, then validate
both seat views, raw/expanded all-in syntax, and +/-1-chip corruptions. These
are512 synthetic validation deals plus oracle/replay executions, not learned
training, policy evaluation, or Slumbot hands. Account for them separately.

Preserve all directed test output, raw oracle hands and per-view validations,
exact commands, source snapshots/hashes/patch, and proof that the concurrently
running pilot's71source pairs are unchanged. Every test attempt has a new output
directory; never overwrite failed evidence. Failures may inform implementation
repair but do not justify changing the512-deck seed or validation criteria.

Success means the standalone terminal validator passes the specified checks.
It does NOT close the remaining request journal/token-chain/session audit gaps,
prove live API compatibility, integrate the old client, or establish strength.
Next integrate it only with a separately registered durable-journal client and
validate complete multi-session evidence before any live qualification.

Exact first command:
python research/experiments/v6-terminal-evidence-validation-20260831/run_validation.py --attempt attempt01
