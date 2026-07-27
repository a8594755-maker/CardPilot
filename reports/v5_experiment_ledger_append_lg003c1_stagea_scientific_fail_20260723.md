# Ledger append: LG003C1 Stage-A scientific fail

Timestamp: 2026-07-23 06:21 EDT

- Diversity treatment completed 5,015,194 new hands with15,194 overshoot. Frozen
  checkpoint SHA
  `a504d118e4999e3a16e3efab552de368f088e7af2a1fede7d6c994440355efba`;
  window audit SHA
  `fa3b2e0a913548668eb89a1fe92b936724233aee8a9866425c2c71d11903531a`
  PASS43/43.
- Mandatory greedy-direct4x1250 produced exactly5,000 hands/32,240 decisions,
  -1,141,475 chips,-228.295bb/100,CI95[-322.4132,-134.1768]. Artifact /
  review / exact-audit SHAs are
  `c157f7ac127b686215aeb2076359ceabd23317680e033b58b782e47a45e28ab9` /
  `d257479d285a086729a12709734e2c69bd037d8bbad25636780fc2dc0d68ab4b` /
  `59a0aeb87930f53564ff9a5034c0687ea23b9c71403e5fb4cf25b83ad8265c28`;
  exact audit PASS113/113.
- Registered gates: treatment-control -96.9456 versus minimum+20 FAIL;
  treatment-historical H11 -82.1224 versus minimum+20 FAIL; treatment absolute
  -228.295 versus strict>-126.1726 FAIL; postflop raise+all-in5051/9202 =
  0.548902 versus maximum0.8 PASS. Any fail freezes
  `LG003C1_STAGE_A_SCIENTIFIC_FAIL_DIVERSITY_WEIGHT_VECTOR_RERANK`.
- Stage B,20k,formal100k and local league-weight/window continuation are forbidden.
  This falsifies this diversity-weight vector, not the whole league family. It is the
  second consecutive scientifically valid no-progress intervention after RS009, so a
  meta-review must switch or fundamentally revise the hypothesis family.
- Pre-refresh AGENTS SHA
  `adc601be84f720bc1abec09f8ea55f1bcdfadd64faf9f1bd11a78f9163847611`.
  Formal H11 remains -100.2475bb/100 CI95[-112.4067,-88.0883];formal hands0;
  strength L0;route exhaustion false;goal ACTIVE.
