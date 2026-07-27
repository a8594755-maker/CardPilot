# LRFT append-only ledger shard

## 2026-07-23 22:10 EDT — LRFT-I00 interface qualification NONPASS

- Identity:
  `a0354ffed044c37ee5cc17a3d045273ecf7751f256a0199f23140d311e55f704`.
- Engine/likelihood/test/result SHAs:
  `9c429ace16f7c70c9ee4723e3b74209acaa6aa320ff117ae7866f4deebcb3b24` /
  `2a9a21e1ba284712ef8c6e29ab4dea45026dce9525c3f2d864d527263a15c183` /
  `300d3d892ce22c9ba48594ed9c619e6f199b72c9532f3c07d8dcf62551823324` /
  `2c30c5570cb39e6b4286f6d5800addf860ec6420c32b3e95a0fd05226883e837`.
- Result18/19. Exact-cent and observation contracts passed4,096 balanced fixture
  rows,36,864 slot attempts,4,096 serial roundtrips,1,280 terminals,8,192
  independently evaluated deals,128 malformed states,192 repeats and75,376
  arbitrary-hole encodings. Frozen V5.5 initial executable table is
  fold/call/slot7-b200/all-in;true BB option,min-raise,short-all-in,reopen,refund and
  zero-sum gates passed.
- Sole NONPASS:single-row H11 inference versus64-row direct batch had maximum
  legal log-probability difference `6.903324072027317e-05`,above the fixed`2e-6`
  batch-shape-invariance gate. No hands,teacher rows,solver roots,checkpoints,network
  or Slumbot evidence were produced. Result has no strength or teacher authority.
- One fresh same-design correction was permitted:fixed batch256 with canonical
  duplicate padding and the unchanged`2e-6` gate.

## 2026-07-23 22:35 EDT — LRFT-I00C1 correction NONPASS and workflow replacement

- Fresh correction identity:
  `5d1ead27b90a8a2485ae4128d602bf26d50c3a42455e7e289a5dd44429b87a6d`.
- Likelihood/test/result SHAs:
  `83d8d1cb81a8a16b5a21f583eccd1334ec6dc6a1bd03466b10b4a12a027c85a8` /
  `bf5d6ca95b9cf1759080cbca03f8649148d67a6e8aee4e4b719e5bb1f9c11a2e` /
  `7c80e5eaae3c4e6f3504c7e57afaea0f3e0d24d1ea4006d83cf18f42e61d603b`.
- Result11/13. Exact fixed-batch256 direct-oracle error is0.0 and4,096 fresh
  observation rows pass. However moving the identical target among fixed-size batches
  gives maximum error`9.787083683931996e-06`;reversing canonical order gives
  `3.505244637835858e-05`. Both exceed the unchanged`2e-6` order-invariance gate.
- This recurrence freezes the arbitrary-order/position-invariant likelihood workflow.
  Do not correct it again and do not widen the terminal gate. The deterministic
  replacement defines likelihood by one immutable compatible-combo canonical order,
  fixed batch256,index position and duplicate-final padding. Reordering is forbidden;
  repeated identical canonical execution,not cross-order equality,is the relevant
  reproducibility contract.
- No behavior,training hand,teacher row,solver root,checkpoint,network or Slumbot
  output occurred. Next is a candidate-specific LRFT-F64 preregistration using the
  revised canonical-order likelihood definition;no additional I00 audit layer.

## 2026-07-23 — LRFT-F64 preregistered and preimplementation-audited

- Fresh identity/token:
  `5d7506904a3846b736d272d13162c2c8c995e36fa6fefbdf88029027a60c8f6b` /
  `5d7506904a3846b736d272d13162c2c8`. Preregistration SHA
  `69f98d90d3b11db67240f2247e2639ed759d0f7254b03e7a726d4136e4c15fbf`.
- The frozen question is feasibility of one depth-two exact-V5.5
  external-sampling MCCFR+ root teacher on64 learner-reached roots. Two identical
  algorithm replicas use disjoint streams,32,768 iterations and snapshots
  2,048/8,192/32,768. E0 selects the smallest fully passing snapshot;sealed E1
  confirms it once. Primary E1 gate is a paired clustered simultaneous-confidence
  lower bound at least+0.20bb per reached root;sampled-BR-gap reduction is directional
  corroboration only. F64 cannot claim GTO,NashConv,exploitability,Slumbot strength,
  teacher-asset eligibility or checkpoint authority.
- The initial independent auditor is frozen NONPASS12/13 because its G3 checker
  required the literal phrase `source hidden cards` while the registration
  equivalently excludes `hidden cards`;audit/result SHAs
  `030d01f87043d0f10767c164958eca90824986648290d86ffa4194e1653fd7c8` /
  `faecd1c939e00e89f0d21da64fd0b0eaa9d56307cd6770bc9afba54d680b44b2`.
  It produced no scientific row.
- The sole fresh simplified C1 auditor independently recomputed the nine contract
  groups and PASS9/9. Auditor/result SHAs
  `5a85e3a9d3da14b83eba29ad84dfb52eed286171353508aeb65c90fab67bdf65` /
  `d568be9aaa8df0ef6af52bef377e4dff398b8db1bf05ce443271e931bd0f7dda`.
  All prospective implementation/output paths were absent and all preexecution
  counts were0.
- PASS authorizes fresh implementation and independent implementation audit only.
  A zero-science exact-kernel resource admission must project the full registered
  workload below21,600s,20GiB RSS,6GiB CUDA allocation and20GB artifacts before any
  census hand,root,belief,solver row or teacher row. Admission NONPASS produces no
  science and forces re-ranking without another performance-probe correction.

## 2026-07-23 — LRFT-F64 preexecution structural design failure

- Terminal failure-report SHA
  `01a41d87ead30d0bec48d35c94efb5899d8c2227e222642b7401c0eed028f1c8`;
  exact status
  `LRFT_F64_PREEXECUTION_STRUCTURAL_DESIGN_FAILURE_NO_IMPLEMENTATION_NO_RERUN`.
- A later independent red-team instantiated the registered estimands and found six
  contradictions that the text-predicate C1 audit did not detect:source-hole-only
  candidate versus full-joint evaluation;undefined two-player utility signs and BR
  maps;unbound census RNG;non-identifiable exact resource work;ambiguous
  logits/probability/CDF math;and ambiguous root-average traversal stream.
- Runner,implementation auditor and output root were absent when detected.
  Resource/model/network calls,census hands,roots,belief rows,traversals,leaf outcomes,
  teacher rows,checkpoints,Slumbot hands and official hands were all0. Both
  implementation workstreams were stopped before materialization.
- This is a scientific-design contradiction,not a path/checker defect. Never
  implement,repair,execute or reclassify F64. It proves no teacher method result and
  does not exhaust the family. Same-turn re-ranking selects a materially revised
  F64R1 only if it separately binds the conditional/full-joint profiles,two-player
  sampled-BR utility maps,identity-derived RNG,exact role/work table,one canonical
  probability routine and one root-average update stream.

- After the absence census but before the stop message reached the parallel
  implementation stream,one52,236-byte runner draft materialized with SHA
  `cc62907cb456523e88ce5b2fc34e721bb1e5b4c312fb4480f192f15b2abe81ca`.
  Supplemental freeze SHA
  `2e537ee3be11cc64e9b72a0810272f5ac45e0e660fd8ade5a5edacb3dc215ff4`.
  It was never imported,compiled,tested or executed;output root absent and all
  scientific/network counts0. Preserve it read-only and forbid any F8R1 reuse.

## 2026-07-23 — LRFT-F8R1 registered and instantiated-audit PASS

- Fresh identity/token:
  `b35078ee7ad2ab123d5f9b0770538793d14e7b9dfbdbb51cc7897df93e2d3198` /
  `b35078ee7ad2ab123d5f9b0770538793`. Preregistration SHA
  `716c074f755d1a377e8752013025392721716d8a456115e7367485afa068b616`.
- This is a fixed-eight-root mechanism screen:16,384-hand public-blind census,
  one root per street×actor cell,two replicas×8,192 external-sampling MCCFR+
  iterations,source-hole proposal rho1/8,one fixed endpoint,E0 4,096 and sealed
  E1 8,192 paired tapes/root. Primary E1 claim is conditional only on the eight
  frozen roots/source holes and requires one-sided95% LCB>=+0.20bb/reached-root.
  There is no sBR,root-population,GTO,NashConv,teacher-asset,checkpoint or strength
  authority.
- Canonical root/belief H11 uses one batch256/index/padding and CPU-f64
  logits-to-probability/CDF routine. The distinct post-root H11-P256 policy uses
  permanent512 lanes,two fixed batch256 chunks,no compaction,profile-independent
  tape lanes and a 73-step Latin translation;each logical branch visits every
  physical position exactly16 times.
- Exact workload is672,896 network calls/172,261,376 rows and at most84,000,768
  exact-cent transitions. A pre-science resource admission must project all work
  below21,600s with1.25 safety,20GiB RSS,6GiB CUDA allocation and2GiB artifacts.
- The first instantiated auditor completed in-memory oracles but left a3,136-byte
  partial JSON when `numpy.bool_` serialization failed;source/partial SHAs
  `22a05e170e42c7efdc9583622d2102bade57580fda2ecb49d1e4b3c14cbd2c3b` /
  `0a308d7caaa5f769d5bce353e675fdc348d85f893faa746f2bbc80e1e11017ae`.
  No science occurred. The sole C1 changed only native scalar serialization and
  output path;source/result SHAs
  `7e64ff98cdbc51e317d8d0af4ee545ebbe0792c16398d37c56794b7d0c267b6c` /
  `d29d30681ea87f90d87e05084630ae9f944383a216c4f619fca0fc2b8b90198c`;
  PASS10/10 independently instantiated probability,RNG,importance,regret,root
  average,lane,pairing,confidence and work-count oracles.
- PASS authorizes fresh-from-scratch F8R1 implementation and independent
  implementation audit only. No model/resource/census/scientific execution before
  that audit PASS.

## 2026-07-23 — F8R1 implementation, preoutput admission failure and C1

- Final F8R1 runner/independent C2 auditor/audit SHAs:
  `2922d9dc18566b361883da6a384a9349a4bddbf5e3f743f0952ba09bbcdd8506` /
  `39f13fec812677cdfdbbc48cd574e7e24c948cd166da9cf6e5bca7ab03e0a3b9` /
  `0fd7c8103b60a4db2795dcfb1bf3eb8f7d04dae575fa25df2d74e6f97e69beec`.
  Audit PASS13/13;two fresh probes each39/39,zero files/bytes,Torch/model0 and
  detailed evidence equal to independently implemented references.
- The one F8R1 resource-admission invocation failed before model construction or
  benchmark because `importlib.metadata.version("torch")` observed registered
  `2.6.0+cu124` while the checker incorrectly expected `2.6.0`. Failure-report SHA
  `99a0f9a65b4c32883cd1967d7c59a0f49380c5cb28ecec4e4298ee5e5726f324`.
  Output root/result absent;model/network/resource/science0. Never rerun or repair.
- Sole fresh C1 identity
  `80f4f9d2e7e6c7f4bc9f6dc82e7f2e896bd0c3ff56dd542eec58b239d1422619`;
  preregistration/preaudit SHAs
  `53b0bbfd1aceb511b7e027fc42e2e100cf6d680f989bf8e292ffd59bf1dccb08` /
  `5857daa842330c7aa5448adce3c57d067b78c9c53ed6f91b0d875e7937a29eab`
  PASS7/7. It changed only fresh control authority/paths and the metadata literal;
  `SCIENCE_MASTER_IDENTITY` remains the parent identity so every science RNG stream
  is bit-identical.
- C1 runner/auditor/implementation-audit SHAs
  `0697f5d127f484f9ad01023d751c87500d527ca3c76a2286e392a04ad1ff0711` /
  `5a1f403ba6202be4bd9bb73ec98cc9a1f62017eb5d1c2154b5fe91cddf2c0aa3` /
  `a236aadacff20657b4e49fa8d69875a876da450e5975ebd089ae1bab9f1304bf`;
  PASS7/7 with normalized full AST equality17,257 nodes,two39/39 zero-file probes
  and parent evidence bit-exact.

## 2026-07-23 — F8R1C1 resource admission NONPASS, science zero

- Sole result SHA
  `6783a63c3026303a4144b8b3a4b08cfa20ed5d91eb194d11f05348368fe3d367`;
  exact status
  `LRFT_F8R1C1_RESOURCE_ADMISSION_NONPASS_NO_SCIENTIFIC_ROWS`.
  Independent resource-auditor/result SHAs
  `3d667fdcf532ba5316b955a4144b3955d7b96f43b3cae94ab4288d228f2bde2e` /
  `1f86e91f3b0341cdb99848b72184f573d5161bb04866c8146b15d5f894d6a0ae`;
  PASS7/7 independently rehashes and recomputes the registered NONPASS.
- Projected wall113,021.17911923451s versus21,600s;this is the sole false gate.
  Bootstrap54,146.759998s,P25624,373.790304s,canonical6,773.813501s,
  transitions4,976.376943s,evidence126.589143s,joint13.874491s. RSS1.136GB,
  CUDA52MB,artifact2GiB,GPU-free,trainer-absence,true-model content isolation and
  zero-science gates all pass.
- Census hands,roots,belief rows,solver traversals,leaf outcomes,E0/E1 tapes,
  teacher rows,checkpoints,Slumbot and official hands are all0. Never rerun,extend,
  tune or performance-probe F8R1C1.
- Same-family reranking selects materially revised F8R2:4,096-hand census with
  28,672-decision cap;two replicas×2,048 iterations;leaf cap8 then a separately
  frozen passive exact-checkdown continuation;E0 2,048/E1 4,096;fixed-root paired
  analytic one-sided CI instead of100k bootstrap. Frozen-rate projection is
  approximately4,808-5,110s,well below21,600s. This is new science and requires a
  fresh preregistration;it is not an F8R1 correction.

## 2026-07-23 — F8R2 preimplementation structural-design failure

- F8R2 identity
  `a424689522962d2a61eab3c530f1fc5daf7fd701f64f22908adb92d3e2978cfc`;
  preregistration SHA
  `e2f8a92c82d238edd7a47e9471a12d943d4940ff0bc95fc2ddbe735532faa563`.
- Independent formula review found that its5,795,840 action-transition cap omitted
  the registered passive exact terminal-closure work. With720,896 outcomes and a
  <=5% fallback gate,a PASS can require up to288,352 additional passive actions;
  fail-closed accounting also needs a6,084,200 terminal cap and180,225 chance/runout
  operation cap. Removing passive closure would change the estimand.
- Failure report SHA
  `cebde5e41eac63b10c1c7f60614f1f58f6bd0348639ef7fb56208c4af61ee996`;
  exact status
  `LRFT_F8R2_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_PASSIVE_WORK_OMISSION`.
  No implementation,model,network,resource,census,root,belief,solver,E0,E1,teacher,
  checkpoint,Slumbot or official hand occurred. Preserve F8R2 and never implement,
  repair or reclassify it.
- Same-turn reranking selects one fresh F8R3 identity retaining the fixed-eight
  hypothesis while explicitly bounding passive action/chance work and projecting
  the larger envelope. Exact-V5.5 teacher remains open.

## 2026-07-23 — F8R3 preaudit structural-design failure

- F8R3 identity
  `d47c166ce97cd20019b0ff31df8045a6334b0430761932fa41a34cb4fef1368c`;
  preregistration/failure SHAs
  `66cfde7ae673d5caff748203f3d8aa88aa5bf011d362c5191d9b64adad709e46` /
  `b6313544da478498eab20520b296d537f34a0d9bf3932dccc332d6e3ec018529`.
- The registered5,109.8081s projection used6,844,416 as the complete padded
  scheduler-operation envelope,but the JSON mislabeled it as base transitions and
  added288,360 passive actions again. The resulting7,132,776 envelope was not the
  projected envelope. Exact complete science scheduler cap is6,264,425,so the
  correct future contract is one total6,844,416 envelope with579,991 operations of
  margin and no second addition.
- Exact status
  `LRFT_F8R3_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_RESOURCE_PADDING_DOUBLE_COUNT`.
  The independent audit task was interrupted before creating any file. No model,
  network,resource,census,root,belief,solver,E0,E1,teacher,checkpoint,Slumbot or
  official hand occurred. Preserve F8R3;never audit,implement,repair or reclassify.

## 2026-07-23 — F8R4 preimplementation structural-design failure

- F8R4 identity
  `165822f101c1da7589cb3a605d16abbc1c2da669f170591b0f9d2ee3c5cedbad`;
  preregistration/failure SHAs
  `b72590708e3f13bf41044fcade01ff13b57a61fa5a9c29adcd267053cef6702c` /
  `9cc0348d223374109bb6cca99fbf1098eeb1cf8fd614039d960c810b24197422`.
- Its E1-open rule requires hashes of candidate,A/B and raw E0 evidence,but the
  prospective path set registered no create-new E0 raw artifact and no explicit
  solver raw/A/B endpoint artifacts. Adding them later changes scientific output
  identity;omitting them makes E0 judgment,E1 binding and result audit impossible.
  Exact terminal status is
  `LRFT_F8R4_PREIMPLEMENTATION_STRUCTURAL_DESIGN_FAILURE_MISSING_E0_RAW_AUTHORITY`.
- The first independent prereg auditor also left a partial JSON while serializing
  `df=+inf` under `allow_nan=False`;source/partial SHAs
  `33163bce36b54903f64f7c75f744db22964da9a5a031479d4e5c2b53221ef8ca` /
  `8dd6a3ed72a2e834d9de8f96abef71a283d2fcfac3583eea13e41d159a817969`.
  This control-plane defect has no scientific authority;its C1 was stopped.
- No implementation,model,network,resource or science occurred. Preserve F8R4 and
  its partial audit. Before any F8R5 registration,run an unregistered read-only
  design red-team of the entire path/schema/phase-binding and work contract.

## 2026-07-23 — Post-F8R4 simplified meta-review selects VR003

- Two independent read-only red-teams found unresolved full-joint teacher
  contradictions in RNG open-interval mapping,E1 isolation,census overflow,solver
  tree/chance work,phase paths and artifact schemas. Under the three-boundary
  simplification guard,no F8R5 was registered.
- Reporting-only meta-review identity
  `5fa7d0f3701e7ea962fb894e536d06969de06d6860e2aa235e8f13e5f99d1305`;
  result SHA
  `4cbdc91ce0cb0d123d8bd1d78e2891643b15bf15887a95511fc10005e484d3e5`.
  Deterministic arithmetic/hash contract PASS selects rank1
  `VR003_RESOURCE_SIZED_FAITHFUL_QBOOST`.
- VR003 must start from exact H11 and never load the frozen VR002C1 provisional
  checkpoint. Its future first-crossing endpoint is1,900,000--1,920,000
  generation-pure admitted complete hands under21,600s. Frozen conservative HPS
  104.44721299953976 plus2,461.7569733s overhead projects20,652.764138s,
  leaving947.235862s headroom.
- A valid audited endpoint must run one complete greedy-direct4x1,250 quick5k
  regardless of mechanism PASS/FAIL. No behavior,checkpoint,network,Slumbot or
  official hand occurred in the review;all four families remain open.

## 2026-07-23 — VR003 preimplementation input mapping failure

- VR003 identity/preregistration/failure SHAs
  `15c162514c345eec0ddeda67d97d3931e13ad65fcad1c3fc20db3ac1c2f750c5` /
  `72bc18693aad9bd0c154cbdd5741240bf2043bae5dad53055727ba40dcab9a27` /
  `2490ebfedca071e71e24744f4e93d922fadf40f37a2c15a7f2ce58294bfc4e6a`.
- Local rehash found the VR002 and VR002C1 preregistration path-to-SHA mappings
  mislabeled. Correct observed SHAs are
  `029411e18760455197471a12f0c00c07d08e6d3123e3d8d62e4b51bc6b7b6fcd`
  and
  `a0a9ff27017257a27cad92bacf2a69f64a1442b218495a3d6d6a76ea7244948e`.
  Exact status `VR003_PREIMPLEMENTATION_INPUT_PATH_SHA_MAPPING_FAILURE`.
- This is a pre-output identity defect:audits,code,outputs,model,training and hands0.
  Freeze VR003. One C1 may correct only mappings and fresh authority/paths;science,
  resource,seeds,endpoint and external gates remain exact.

## 2026-07-23 — VR003C1 structural NONPASS; simplify to VR004

- VR003C1 identity/preregistration/failure SHAs
  `ad4f8d47e084a2e47c8f64efae465fd816d5af5d7dc4448cbe8392a9498b6a3a` /
  `c2b3eb558db0e8855fafc15645103e6eae3c43a9ac9e09d62853b4a0858f5ffd` /
  `a1ee63277ff4c59e82e9282ddc8c1a647b2c53807101522224091c8ed95d74aa`.
- Independent red-team found undefined semantic projection,fresh assignment-seed
  conflict with hardcoded parent selector,watchdog/launcher contradiction and no
  prospective upper bound on pipe-drain endpoint overshoot. Exact status
  `VR003C1_PREIMPLEMENTATION_STRUCTURAL_NONPASS_SIMPLIFY_TO_VR004`.
- An audit draft was materialized before the stop but never executed;SHA
  `2e3ff632e3713ce919a107b2476f23c5c403c18ab904d29f034d5a390a474416`.
  Audit report absent;implementation,model,training,checkpoint and hands0.
- VR003 correction allowance is consumed. New-design VR004 is selected:exactly116
  updates with exactly16,384 admitted-pure hands each (=1,900,544),fresh standalone
  assignment selector,fresh Python monotonic supervisor and targeted executable
  contracts. Frozen conservative projection is20,657.972511s under21,600s,
  headroom942.027489s. Valid endpoint requires audited quick5k.

## 2026-07-24 — VR004 structural NONPASS; goal workflow redesign required

- VR004 identity/preregistration/failure SHAs
  `94e75a5e4df38d2ff7270e0a3ef5a6edfddd4db4f0d1e70bd0ff8bb2c749675b` /
  `2923e5fb20cd0d94331ff24b093864263ea6293f7c1779e84fe6fd1134bc04ff` /
  `61ade49bc152b1c89e6d475b71df52a12fdc595397d94214a53de7fa1110f873`.
- Independent red-team found the behavior config underfrozen,the fresh per-hand
  selector changed the measured per-update opponent/batching topology and conflicted
  with mirrored self-play,the FIFO packet protocol lacked a global reconstructable
  order,and the supervisor/evidence graph was incomplete. Exact status
  `VR004_PREIMPLEMENTATION_STRUCTURAL_NONPASS_WORKFLOW_REDESIGN_REQUIRED`.
- The prereg audit was stopped before script/report materialization. Implementation,
  model,updates,training,checkpoint,Slumbot and official hands0. This is not Qboost
  science.
- Repeated thin-overlay preregistrations are now identified as the workflow root
  failure. The next goal design must require one content-addressed executable
  experiment package containing config,topology,packet protocol,supervisor,evidence
  schemas and verifier,with parallel preflight work inside that package and one
  registration only after the package is executable.
