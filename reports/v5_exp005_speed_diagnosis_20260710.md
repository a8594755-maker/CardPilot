# EXP-005 Speed Diagnosis

- Decision: `CONTINUE_SPEED_GATE_CURRENTLY_PASS`
- Checked at: `2026-07-10T18:57:12.992967+00:00`
- Cutover hands: `515,989,661`
- Baseline exact actual-hand window: `495,989,661..515,989,661`
- Baseline rows/effective h/s weighted: `1216` / `1457.517`
- Candidate tail rows/effective h/s weighted: `60` / `1499.908`
- Effective weighted ratio: `1.0291` (success `>= 0.90`, abort `< 0.85`)
- Collect h/s ratio: `0.7510`
- Inference batch ratio: `0.3766`

The lower inference batch size is real, but PPO time is also lower; the registered gate uses effective wall-clock throughput. This is a provisional operational diagnosis, not the terminal 20M method judgment and not strength evidence.
