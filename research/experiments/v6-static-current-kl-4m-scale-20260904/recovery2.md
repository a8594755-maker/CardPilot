# Recovery 2: external process interruption

Recovery1 was verified through eight new completed updates (iterations 769-776),
but its process later disappeared while `run_manifest.json` still said `running`.
No `train_v5.py` process remained in the OS process table.  Therefore this was
an external process interruption, not a runtime guard and not a training failure.

The last complete checkpoint, metric and assignment boundaries agree:

- frozen source: `recovery_sources/seed2_recovery1_interrupted_iter776_hands3196923_physical3657838.pt`
- SHA256: `3fd0959095f62f19f2de0541e4bbda24735b6cf288001efa7f0b6f98691dd700`
- iteration: 776
- transition-bearing hands: 3,196,923
- completed physical environment hands: 3,657,838
- optimizer: 10 state entries, stored LR `1e-4`
- PPO replay: serialized iterations 775 and 776, RNG present, cumulative rows
  5,640,663
- active loss-kbest pool: `[0, 1, 2, 122, 206]`
- metrics prefix SHA256:
  `ff5a21f8d7cbfe58a473369890767a910cab4f1415527f12a5184d01a194eb82`
- assignment prefix SHA256:
  `631159dd625b78a4b166c16e5eaa7f7e0d48f875bea11543e165a8ea476222f3`
- pending assignment 777 SHA256:
  `8e9980b429d99e645136cbae7b5298b1f899d65a0d6d2e06a43c84bfc3d94a39`

Recovery2 resumes this exact source with the unchanged method, seed, worker
seed, fixed deal-stream start, optimizer, replay, assignment recovery and 4M
physical target.  Work not represented by the completed iter776 save is not
counted or reconstructed.  Existing evidence remains append-only.

