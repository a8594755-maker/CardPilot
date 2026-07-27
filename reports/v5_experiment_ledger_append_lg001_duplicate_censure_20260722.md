
## 2026-07-22 16:25 EDT - LG001 late duplicate registration CENSURE

- Event ID: v5-lg001-late-duplicate-registration-censure-20260722.
- Classification: LG001_LATE_DUPLICATE_REGISTRATION_FAIL_CLOSED_EARLIER_TOKENIZED_REGISTRATION_REMAINS_SOLE_AUTHORITY.
- The earlier tokenized LG001 preregistration/audit SHAs are 2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125 / 92dd02a8770035c5698edcc7288d8d8ea214c1ce465c8b3ad0a5eb0d07e666e9, reported PASS91/91 under token 5ee42cb09c534cb3a294be701e94047f. Both were complete before the later preregistration path was created, so this pair remains the sole LG001 registration authority.
- The later incompatible preregistration/audit SHAs 6881da78f49633afbebdd73dc137961b4cfd81885f1dee745dce2c8c84b52067 / 4d8c41e6cb37e20b6d8a67eb21fa2b40b637088ed6cc2c8886f446d7d545e0d8, reported PASS100/100, have authority NONE and are provenance only. Their prewrite claim of zero alternate LG001 registrations was false because the tokenized pair already existed; the later audit omitted that pair.
- CENSURE SHA256: 840e898f2717ef5c5134f43a9a14a1f3c104e3e9066571ae8bb9cab7b774fa24. Preserve all four files without mutation; no implementation, result, training, evaluation or successor may descend from the later pair.
- No LG001 implementation file, output root, active window, training arm, checkpoint change, Python trainer, Slumbot process or official hand exists. Strength remains L0; goal ACTIVE/incomplete; route_exhausted=false/unjudged.
- Next later only: one token-bound implementation from the earlier authorized pair, proportionate independent implementation audit and zero-output deterministic contract tests; stop before training. Implementation, preflight, training, GPU training, evaluation and Slumbot authority are NONE now.

