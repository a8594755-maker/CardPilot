# Conservative soup generic-greedy fresh5k Slumbot

Freeze exact candidate SHA256
`914c8d186d4cdb4f2139ff64d2b32b7558eb1c5761b553c09457bd756aaec8e5`.
Run exactly eight new independent 625-hand journaled sessions with seeds
2026110501--2026110508 and generic greedy execution.  No restart,
supplementation, pooling, alpha search, score stop, checkpoint change, or mode
change is allowed.  Earlier parent, Standard10, and candidate hands are
excluded and cannot be pooled.

Audit raw hands, terminal counters, model decisions, policy mode, token-chain
and session independence.  Recompute bb/100, raw-hand CI and session-t CI from
raw JSONL.  Admit only a separately logged fresh20k if the completed fixed pilot
has positive raw bb/100 and at least four positive session means.  This 5k pilot
cannot satisfy the Goal.
