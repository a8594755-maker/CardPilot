# V5 Pre-500M Method-Selection Diagnostic

- Checked at: `2026-07-10T06:03:13.870363+00:00`
- Current priority: `EXP005_STRUCTURAL_PRIORITY`
- Selection status: `WAIT_FOR_500M_OFFICIAL_PROMOTION_RESULT`

This is read-only decision support. It does not authorize a behavior change and does not prove strength.

## PPO Stability (EXP-006A)

- Rows: `1000` (`26364..27363`)
- KL mean / median / p95 / max: `0.0512` / `0.0403` / `0.0957` / `0.7175`
- KL > 0.03 fraction: `0.902`
- KL > 0.10 fraction: `0.049`
- Clipfrac mean / p95: `0.245` / `0.330`
- Isolated EXP-006A support: `False`

## Opponent-Distribution Instability (EXP-005)

- Exact gate warning counts: `[1, 2, 4, 4, 6, 0, 2, 2, 7, 2]`
- Warning range: `7`
- PASS/WARN switches: `2`
- EXP-005 structural support: `True`

## Decision Boundary

- No method cutover before the official 500M promotion result.
- A strong promotion launches formal100k, not a method experiment.
- A non-strong result requires the full loss review before exactly one separately registered cutover.
- When both signals persist, isolated KL early-stop is ranked first because KL is directly measured; group assignment remains the structural follow-up candidate.
