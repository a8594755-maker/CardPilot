# Offline v6 external-evidence protocol result

Ten fixed cases exercised the actual client main/play_one with a toy policy and offline native-rules server. No network, learned-weight update, training hand or performance-evaluation hand occurred. This is protocol evidence, not an independent rules-oracle or policy-strength test.

Completed prefixes, counters/arithmetic, failure propagation/no retry, sampled decision replay, token redaction and source immutability passed. The following block future external qualification:

- missing_attempt_journal: Only completed hands and aggregate summary persist; failed attempt/request intent and partial decision trace exist only in the diagnostic server transcript, not client artifacts.
- terminal_bounds_not_enforced: Integer winnings beyond the200bb zero-rake bound are accepted as completed hands; downstream evidence qualification must reject them.
- terminal_history_not_validated: Winnings on a nonterminal action prefix are accepted without a terminal-state consistency check.
- token_transition_not_persisted: Client follows rotated tokens but only persists the initial token hash for each completed hand; no request-by-request transition evidence.

Production sources remain unchanged because the active curve owns its snapshot. Defer a separately registered repair and external-evidence/session-auditor validation until that run is terminal. No external admission is granted by the current audit.
