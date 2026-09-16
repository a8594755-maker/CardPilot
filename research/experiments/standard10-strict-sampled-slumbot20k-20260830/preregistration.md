# Frozen Standard10 strict native-sampled external baseline

Registered before any external hand. This evaluates the unchanged learned weights with their native sample/temp1 action distribution; it is not a temperature search, learned-weight treatment, scripted poker strategy, or promotion of the unsuccessful large-batch regimen.

## Fixed design

- Frozen source SHA256:91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428. Copy once to `frozen/standard10.pt`, verify hashes before/after all work.
-200bb HUNL; strategy=model; policy-mode=sample; temperature1; v4 observations; no policy guards/overrides or ensemble.
-8sessions,2500requested hands each; seeds2026090601 through2026090608. Each new client starts without a Slumbot token. Start the next client only after the preceding client has one complete raw hand and a decision dump, plus1second stagger. Eight sessions is the maximum concurrent load.
- CPU inference,1intra/inter-op thread per client. Freeze the complete Python execution source before launch; use that snapshot for clients/audits. A zero-hand snapshot loader must pass before the first external game.
- One immutable output directory and one process per session. No retry/restart/reseed/supplement/replay after terminal errors. Existing evidence is never overwritten. A180second first-hand readiness guard and10800second total guard are operational bounds,not score-based stops. On guard or terminal failure preserve all evidence and stop only owned live clients,then diagnose; do not pretend incomplete work reached20k.

## Accounting and validation

The sole wrapper scans new complete raw JSONL rows and updates experiment evaluation_hands at most about15seconds after observed growth, plus after every terminal event. That count is completed raw-reward rows,not requested attempts or API calls. Incomplete tails are buffered and final malformed/truncated evidence is rejected. All attempted/successful indices, chip/bb/cumulative totals, result CIs, model/mode/temp/seed identities and dump rewards must reconcile under the strict new-run audit. Any fallback/missing trace, incomplete session, failed hand attempt, duplicate file or repeated observable deal stream makes the run ineligible for promotion. All raw records remain preserved and counted as work even if the run is invalid.

Use action-independent initial-card/seat replay checks as an observable diagnostic,not proof of hidden-deck independence. Model/manifest/code/input hashes and command/launch/exit metadata are retained. No tokens are logged. Readiness polling never bases decisions on winnings.

## Analysis and next-step rule

Primary: raw unadjusted mean bb/100 with1.96sample-standard-error95% CI over the fixed20000 hands. Also report per-session point estimates and a session-mean Student-t interval(df7), clearly a sensitivity analysis with only8clusters. Do not replace the primary CI with a more favorable one. Historical Standard10-11.4275bb/100 was greedy and is not a matched comparison for this policy.

If and only if all evidence is valid/complete and raw point estimate>0, admit a separately preregistered fresh100000-hand frozen-policy formal test; a positive20k CI alone does not satisfy the goal. Never pool these pilot hands or old greedy hands into that test. If the point estimate is nonpositive, do not extend this pilot; select subsequent general learned-weight work from the evidence. No checkpoint or policy-mode reselection within this experiment.

The wrapper leaves the same record RUNNING after its terminal analysis for review/finish. Goal success remains at least100000 fresh Slumbot hands for one unchanged policy, bb/100>0 and95% CI lower>0; this pilot cannot establish it.

## Validated transport and excluded parent

Use `--strict-policy-execution` for every client and the zero-hand loader. It forbids fallback actions and stops immediately on any hand failure before requesting another hand. `persistent_session_no_retries_v1` reuses a per-process HTTP Session, retries no POST, refuses redirects, consumes/closes responses, retains no cross-call cookies and keeps TLS verification enabled. Both raw rows and summaries must declare strict mode and the exact transport identity; the manifest declares this contract. Strict evidence audits must enforce it.

The previous `standard10-native-sampled-slumbot20k-20260830` pilot was infrastructure-aborted outcome-blind at4,168complete raw hands. Its partial outcome was examined only after its stop. None of those hands, sessions, tokens or seeds is reused or pooled here. The transport repair completed83offline tests and a real zero-hand model load; it establishes local client semantics,not server persistence or a proven global port-exhaustion cause. This new trial may not be resumed or extended on failure, irrespective of observed outcomes.

