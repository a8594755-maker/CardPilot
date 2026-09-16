# Isolated regression for inline Python command provenance

The active physical1m record has two literal, successfully executed multiline
Python archive checks. The legacy command classifier flattens whitespace and
mistakes a less-than comparison followed by a greater-than comparison for an
angle-bracket placeholder. Raw commands and execution evidence must be preserved.

Scope: develop an ISOLATED candidate classifier for a deliberately narrow literal
Python inline-command form; parse source with ast, never execute it. Keep legacy
classification for other commands. Valid dictionaries/comparisons and descriptive
words inside executable Python are not shell placeholders. Placeholder strings,
standalone ellipsis, invalid syntax and unsupported/interpolated quoting must
remain flagged. Classification is syntactic provenance triage, not proof that a
command will run or is safe to execute.

Before applying to any record, test fixed positive/negative fixtures, including a
side-effect payload that must NOT execute. Snapshot the active record's commands
once, verify that only the two known false positives change and every other
classification is identical. Retain candidate code, source hashes/patch, command
corpus, regression outputs and exact commands. Verify all76active source/copy
pairs and all4frozen curve identities remain unchanged.

Zero training/evaluation/Slumbot hands, zero model queries or network calls.
Do NOT replace research/experiment_log.py, rewrite old commands, edit the active
record's classifier metadata, or touch any current evaluator/checkpoint/raw pairs.
Deployment is deferred until after the current matrix's final review. A passing
candidate does not make the still-active legacy audit warning disappear.
