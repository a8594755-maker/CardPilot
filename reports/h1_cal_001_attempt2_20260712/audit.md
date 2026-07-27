# H1-CAL-001 Immutable Holdout Audit — Attempt 2

- Status: `PASS_IMMUTABLE_HOLDOUT`
- Pairs / hands / decision rows: `10,000 / 20,000 / 48,533`
- Zero-decision completed hands: `1,210`
- Errors: `[]`
- Training use: `FORBIDDEN_HOLDOUT_ONLY`
- Launch authority carried by this audit: `NONE`
- Official hands authorized: `0`

## Frozen identity

- Source checkpoint SHA256: `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`
- Deal seed: `2026071111`
- Manifest SHA256: `0ce91c7199cd885d7f29e75f5c75810b11a8410ca1eac57ab15ca2cc63db3342`
- Hands SHA256: `ed2323785b1f14f628c22c79723febb84762badcf7a2e96801e9ded45f3b332a`
- Decisions SHA256: `4eec2dc6b7f1063b7f0e5f5d00bc02a46c14342f35f004b431c5f2cf60d5c150`
- Summary SHA256: `f5073d2e3d890f16022669ade652a688bc69cef812a8b0397fe84af9e8918e44`
- Audit JSON SHA256: `1cba9b8741f5caa6b1f2bb500e5e998bf6b7681219bc8d911bafbd7792538f4a`

Attempt 1 remains terminal `FAIL_CLOSED_MISSING_HAND_LEVEL_COVERAGE`. Attempt 2 uses the identical frozen deals and identical decision payload; it repairs only evidence coverage by recording every completed `(deal_id, source_seat)` hand, including hands with zero source decisions.
