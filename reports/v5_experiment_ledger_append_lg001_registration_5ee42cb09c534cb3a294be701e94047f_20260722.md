# V5 append-only experiment ledger shard — LG001 unified behavior-window registration

## 2026-07-22 16:45 EDT — same-start diversity-weighted opponent-league experiment registered

- Event ID: `v5-lg001-unified-window-registration-5ee42cb09c534cb3a294be701e94047f-20260722`.
- Preregistration/audit SHAs `2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125` / `92dd02a8770035c5698edcc7288d8d8ea214c1ce465c8b3ad0a5eb0d07e666e9`; independent audit PASS91/91 after 16/16 evidence rehashes, exact H11 checkpoint inspection, all five state-dict hashes, H4 edge/weight recomputation, config comparison and fresh-path checks.
- Post-entry singleton adoption `23bfa84b...b2e0d` is compatible: it confirms the earlier `11a155c5...b94599` CENSURE as sole authority and the same fresh LG001 next boundary. Neither RR033 result is used.
- Source is exact H11 endpoint SHA `96a00703...ca13`, iter35051, 576,021,901 hands, with optimizer and five frozen pool members IDs103/109/115/120/129.
- One causal intervention is tested: conditional opponent-pool weights. Both arms keep self-play0.20, freeze the same pool, preserve model/optimizer/PPO/environment/deal stream, and use per-iteration assignment. Control pool weights are uniform0.20 each. Treatment weights, recomputed prospectively from mean absolute H4 common-deal edge bb/100, are ID103=.1513316310,109=.2726794516,115=.0625033687,120=.3251180109,129=.1883675378.
- Stage A runs sequential same-start 5M-hands control and treatment arms. Both endpoints require complete greedy-direct Slumbot quick5k bundles. Stage B treatment-only continuation to20M total is authorized only if treatment improves by at least20 bb/100 versus both same-start control and historical H11, exceeds -126.1726 bb/100, and greedy postflop raise+all-in is at most0.80.
- Stage B also requires quick5k. A later 20k registration is permitted only if its quick5k exceeds +25 bb/100 with the mechanism gate and complete bundle. Quick5k is directional only;formal100k authority remains NONE.
- Implementation must be opt-in in the actual V5 trainer, disable pool mutation only under the LG001 contract, use one deterministic SHA256 assignment draw per absolute iteration shared across arms, and emit hash-chained assignment provenance. Default/core training behavior and network are frozen.
- No implementation,contract test,training,checkpoint,GPU,evaluator,Slumbot or official hand ran. Output/code paths remain absent;L0;route exhaustion false/unjudged;goal ACTIVE/incomplete.
- Next later only:LG001 implementation plus proportionate independent implementation audit and zero-output deterministic contract tests;stop before training.
