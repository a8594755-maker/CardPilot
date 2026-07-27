# H3-DATASET-SAMPLE-001 draft

Status: `DRAFT_PRE_PROFILE_NO_AUTHORITY`.

The full 600-board corrected-QA gate remains mandatory. Materializing every source
info-set would require about 16.623 billion tensor rows and 50.316 TiB uncompressed, so
this draft freezes a feasible deterministic selection rule before the first corrected
board profile is observed.

Candidate budget: 30,000 rows per board, at most 18 million rows and about 55.8 GiB of
raw float32 tensor payload. Rows are stratified by street, player and CFR action count.
Every nonempty first-board stratum receives a base quota; remaining rows are allocated
by square-root population weights with deterministic Hamilton apportionment. Within a
stratum, the lowest seed-keyed SHA256 ranks win. Later-board shortfalls are reported and
never reallocated.

The exact quota map is deliberately not frozen until the chronologically first corrected
QA-PASS board supplies its identity-bound population profile. This draft authorizes no
dataset materialization, H3 behavior, critic supervision, official hands or strength
claim.

