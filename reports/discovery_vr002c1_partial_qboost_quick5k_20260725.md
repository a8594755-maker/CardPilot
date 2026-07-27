# Discovery experiment: VR002C1 partial Qboost quick5k

- Started: 2026-07-25 America/New_York
- Evidence class: diagnostic discovery; not promotion or formal strength evidence
- Hypothesis: the partially trained centralized-Q9 Qboost actor may show enough
  external improvement over H11/CT003 to justify a clean hardware-saturating Qboost
  continuation or rebuild.
- Candidate:
  `models/alpha_holdem_v5_hybrid/v5_vr002c1_8d3cb2f1a897d1b9228b14ee7043db49_20260723/vrpo_stagea/latest.pt`
- Candidate SHA256:
  `e6aa5c972ab4b0864ba5159d1a740edd8e8f82a71f4f90639597ef2cc427cadc`
- Candidate state: iteration 35,212; total hands 579,086,001. This checkpoint came
  from an historically invalid partial endpoint and is deliberately evaluated only
  as a diagnostic research candidate under the 2026-07-25 autonomy charter.
- Evaluator SHA256:
  `d44b21b1f91c8f824efa58ce1e897457905ecda160b5557b468027077fb6aa04`
- Launcher SHA256:
  `3bdff2ba58da2d449a42d2f488ce70fd101d6eb5c4156da67fee111b2447162f`
- Policy: V5.5 observation, greedy-direct, CPU
- Budget: four independent sessions of 1,250 complete Slumbot hands, exactly 5,000
  hands total; no post-hoc extension
- Output:
  `models/diagnostic_vr002c1_partial_quick5k_20260725`
- Decision:
  - clear material improvement over H11/CT003: prioritize clean Qboost training;
  - no improvement: abandon local Qboost continuation and switch to an architecture
    or teacher intervention with larger expected effect.
