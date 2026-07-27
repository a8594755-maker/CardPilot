# CFR32 reconstruction config mismatch

- Status: `INVALID_INPUT_RECONSTRUCTION`; preserved for diagnosis only.
- Original CFR source: `data/cfr/pipeline_v3_hu_srp_200bb_legalallin_v2`.
- Source metadata config/stack: `pipeline_srp_v3_200bb` / `200bb`.
- Invalid converted dataset:
  `data/training/cfr_v55_compact_200bb_flops32_sample05_20260726`.
- Invalid converter config: `pipeline_srp`, which reconstructed the 200bb
  histories with the 50bb tree and produced states with roughly 45bb remaining.
- Invalid derived checkpoints:
  `models/v5iter4800_preflopraw256_cfr32_anchor10_3m_20260726`.
- The just-started external screen was stopped after 80 total hands, before its
  score was inspected, and is not a 5k result:
  `models/bench_v5iter4800_preflopraw256_cfr32e1_pure_fresh5k_20260726`.
- No environment training hands were added. The invalid distillation used
  6,868,649 offline decision samples and inherited 78,760,653 lineage training
  hands.
- Fix: `cfr-to-training-data.ts` now fails before output creation when selected
  board metadata config differs from `--config`.
- Replacement conversion:
  `data/training/cfr_v55_compact_v3_200bb_flops096_balanced_20260726`, using
  `--config pipeline_srp_v3_200bb`; its startup log confirms source metadata
  `configs=pipeline_srp_v3_200bb stacks=200bb`.

The single-board dataset
`data/training/cfr_v55_compact_200bb_pilot_board1_sample15_20260726` already has
the correct `pipeline_srp_v3_200bb` manifest and is not affected by this defect.
