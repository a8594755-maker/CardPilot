# Standalone terminal evidence validator

Decision: STANDALONE_TERMINAL_VALIDATOR_VALIDATED. This is not client integration
or external qualification admission.

The first preserved attempt passed19directed unit tests and512fixed synthetic
deals (seed20260922). Each deal's4256total native decisions were checked against
the pinned PokerKit0.7.5 oracle adapter; terminal coverage was189folds,323showdowns,
including15ties. Both seat views produced1024accepted terminal records. An
additional182expanded all-in suffix views passed, and all2048plus/minus1-chip
reward corruptions were rejected. The validator also rejects nonterminal
histories, malformed separators, invalid/duplicate cards, inconsistent boards,
invalid types/bounds, undisclosed showdown cards, changed request context, and
unsent additional client actions.

The downloaded primary API sample from https://slumbot.com/sample_api.py has SHA256
17ab1f6c1a25db1822cef7f34ed67b6516ac65ea24897adcc92d8f2db8f71505.
Its inspected ParseAction function corroborated valid terminal wire syntax; no
HTTP,login,strategy or main function from that sample was executed. The runtime
validation blocked network connections. Public documentation retrieval did not
create a poker session or hand.

Independent post-run inspection verified all3raw output hashes,512raw oracle
rows,1024seat-view rows and their exact per-seat payoffs/corruption counts.
The run verified23own source pairs and71unchanged source pairs belonging to the
concurrent source-KL pilot. All validation outputs are retained in attempt01.

No learned policy was evaluated or trained: new_training_hands,evaluation_hands,
and slumbot_hands are all0. The512oracle deals,local reconstructions,terminal
validator calls and directed fixture cases are diagnostic executions,not new
independent benchmark deals or evidence of policy strength.

Only the new standalone scripts/alpha_holdem/slumbot_terminal_v6.py was added.
Existing client,inference,training,checkpoint and captured helper files were not
edited. Request/partial-hand journaling,hashed token-transition evidence,
multi-session auditing and an integrated-client failure suite remain required
before any external qualification. Missing showdown cards must cause a preserved
failure,never a guessed payoff,retry,selective omission or replacement hand.
