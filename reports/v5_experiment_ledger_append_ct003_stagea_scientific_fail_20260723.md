# Ledger append: CT003 Stage-A scientific fail

Timestamp: 2026-07-23 10:03 EDT

- Boundary: `CT003_STAGE_A_SCIENTIFIC_FAIL_MC_VALUE_TARGET_RERANK_TO_FAITHFUL_VRPO_QBOOST`.
  CT003 identity `7296402ab1ddaadd86ebde1795d0f2ade6f8c609f8f13aa1c41035c6470761a0`
  changed one causal variable from exact H11/LG003C1: the existing scalar value
  critic received full-hand Monte Carlo targets while actor advantage/objective,
  actor information/interface, opponent assignment, pool, deals, and seeds stayed
  fixed. Preregistration/audit/implementation-audit SHAs were
  `7702ff2d7323bcb053443a7b1e540e4624f43e3d932bfd2c3ecbb7afb0bb11fe` /
  `8ffdf4cd3f16790a1fb3435b402c7e2526fc1558aa6dccf4f51cd2ef786801db` /
  `67e4857350df2158ad11424503b6a7114e4878d7ec711c3861d1b26e8acff9d9`.
- Stage A completed 5,016,244 new hands at iteration35,356; overshoot16,244 was
  below the registered50,000 cap. Checkpoint/raw metrics/provenance/manifest SHAs
  were `76b85c5bd377533329424140d01352075e44b6a1aeb5796828fee60f34037f62` /
  `21d63aaadb114cb630227eab3b8cf8dc02993c2ed898bf2491d02f65933ed8d1` /
  `93f6d8c252738d9f95fdde016222e01e3878ff93984e2ca259a4102bd5fa967d` /
  `87ad99f17c020d5dd31812851dd5ab3a84fa61bb8fbc93dd4721e0351ccc4fa2`.
  Target coverage was1.0 and throughput/control was1.0882113.
- The original frozen window auditor produced FAIL23/24 solely because it read
  uniform weights from a wrong derived-report field path; result SHA
  `63ac2e1bfbca08846dbbb6c1154bc7a132d44a63a8d4bf082cf84d1af5bafb66`.
  This is preserved as a reporting-only control-plane defect. The one fresh C1
  auditor source/result SHAs
  `f0e97e68d869c131b01c149604d603fd4b3e748918f2a0620f0128a8f2a69aa6` /
  `381dc18654c1545880ed4a9990cc8f9c57cd5d9e0036edbfe1d8f9957b3b2b52`
  passed23/23; supplemental independently implemented full-pool-state and
  provenance-tail audit SHA
  `1e25bf19df2f7d5185a7fae6b49e61ff174b5d530ac35440905ff213016f0ea8`
  passed8/8. Training was not rerun.
- Mandatory quick5k identity
  `f17e35db285d0af29f2319856dd9b5a0dc9ba66275c8b57aed7093a422e590ed`
  used the exact checkpoint, greedy-direct CPU policy and4x1,250 complete hands.
  Registration/prelaunch-audit SHAs were
  `d152cef07025e4933fba7058174ababe33227202c2a92db75154b0dd5851f478` /
  `6e64d45ae2c9ddec9b9fe8d9bba568b74a11d3b98eeb10efd17b12131397139c`.
  It produced5,000 hands/27,188 decisions,-727,310 chips,-145.462bb/100,
  CI95[-227.9171,-63.0069].
- Artifact-audit/hand-review/exact-result-audit SHAs were
  `1a92875734f277d48ba1c630a405def1a03bb084f6a6a2017f2391383650ad4a` /
  `f724c73840f877384655813b29c414a508360e0599a1d41fa8c52efb0e353fd0` /
  `7b2efc434046f0835b842c97a6253055bd6cc8577d84e95a3028c4358862c0dc`;
  exact result audit PASS113/113. Registered gates were treatment-control
  -14.1126 versus minimum+20 FAIL, treatment-H11 +0.7106 versus minimum+20 FAIL,
  absolute -145.462 versus strict>-126.1726 FAIL, and postflop aggression
  2342/7004=0.334380 versus maximum0.8 PASS.
- Judgment/audit SHAs were
  `39b2b1276d69ac2583c3f1fa2890c4cac0d6c9bc6041a72c1e567655579d25c3` /
  `7ef0fa481aa9e0a93f51e6442cbd753da15e84f31b07fcd2680701d62bf404b8`;
  the independently implemented deterministic judgment audit passed12/12.
  Never rerun,extend,repair,adopt or continue CT003;15M,20k and formal100k are
  unauthorized.
- CT003 falsifies only full-hand Monte Carlo targets for the existing scalar value
  critic. It did not test centralized nine-action Q, policy-expectation Vpi,
  Expected SARSA(lambda=.95), Q-boosted actor advantages, or faithful VRPO. Rank1
  is now one fresh exact-H11/LG003C1 same-start faithful VRPO/Q-boost intervention
  with official actor/evaluator unchanged. The exact-V5.5 learner-reached
  full-distribution teacher, adaptive payoff league and PBS resolver remain open.
- Pre-refresh AGENTS SHA was
  `d708f2ee1a1d5944cece7b1e1a961684d8e3f06a1c863089bfd252f2d6217db2`.
  Latest formal H11 remains -100.2475bb/100 CI95[-112.4067,-88.0883];
  formal claim hands0; strength L0; all four families remain scientifically
  unexhausted; route exhaustion false; goal ACTIVE.
