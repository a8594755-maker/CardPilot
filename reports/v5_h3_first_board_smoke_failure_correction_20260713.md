# H3 first corrected-board smoke failure correction

Board 6 itself passed the corrected solver QA. The first adapter smoke failed closed and
its complete partial bundle is preserved at
`reports/h3_first_board_smoke_20260713.interrupted-1783926755`.

The failure was in the offline adapter boundary, not the CFR solve. Python replay first
restored a previous street's raise count after a call advanced the street. Once that was
fixed, the preserved smoke exposed a second invalid assumption: Path-1 and the separate
Python HUNL state can legitimately enumerate different stack-deduplicated raise counts at
deep nodes. Requiring their action strings to be exactly equal was stricter than the v2
design lock and rejected valid source rows.

The corrected exporter now uses the already-locked Path-1 replay and exact realised
amount mapping to bind each CFR action to one v5.5 actor slot. The adapter independently
checks action semantics, corrected probability mass, the coalesced target, actual v5.5
legal-mask support, OOD provenance and actor-only scope. It does not relabel the synthetic
entry as reachable and grants no behavior or official-hand authority.

The corrected bridge, adapter, exporter and smoke-supervisor identities are recorded in
the matching JSON artifact. Tests pass 17/17, 38/38, 10/10 and 15/15 respectively. Retry
PID 6520 is BelowNormal and CPU-only; its terminal result remains fail-closed.
