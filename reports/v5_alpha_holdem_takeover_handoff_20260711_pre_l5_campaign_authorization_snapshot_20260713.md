# AlphaHoldem V5 HYBRID Takeover Handoff

Checked: 2026-07-13T04:06:15.0277867+00:00

- H1 is terminal **FAIL**. critic_v2 is rejected; exact gate31400 critic_v1 remains the selected rollback/H2 source.
- Control endpoint: iter32617 / 536,004,082, SHA f3bc22de78caa4cc10493fdf6d8c4b09a4c3f6ec67c2e20ceba276ff76bba6b8.
- Treatment endpoint: iter32617 / 535,996,488, SHA 4c021cbf9f25aeefa81b29c823bd7ec0b94bd87668cc7a4e1320d3c662588274.
- H1 value result: -2.1985% MSE reduction, bootstrap95 CI [-6.4167%, +1.7948%]. Full throughput ratio0.826652 also fails; entropy guards pass.
- Completion audit reports/v5_hybrid_h1_completion_audit_v2_20260713.json is PASS_COMPLETE_H1_TERMINAL_FAIL, SHA d00c482b63817e251707a20947d44901754b90b3831e8e8c9584119278560f8b.
- H2 draft is complete but has **NO launch authority**: reports/v5_hybrid_h2_preregistration_draft_20260713.json, SHA b450ccb93de36c08fa064cc938693ef7c499942e6a7bfa080144997fe2ef5ca2.
- Path-1 is CPU-only RUNNING at 156/600 boards, PID51176, six workers, 80K iterations. Leave it running.
- Official strength remains L0: 20,400 greedy-direct hands, -153.2999 bb/100, CI[-187.6945,-118.9052]. H1/H2/H3 authorize zero official hands and no strength claim.
- Next valid work: close H2 draft prerequisites and, only after review, publish a separate immutable preregistration/design lock. Do not launch H2 automatically.