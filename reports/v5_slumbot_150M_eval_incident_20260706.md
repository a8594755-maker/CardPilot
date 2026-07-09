# V5 Slumbot 150M Quick5k Eval Incident - 2026-07-06

## Scope

- Run: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- Frozen checkpoint: `models/bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_150M_quick5k_cadence_checkpoint.pt`
- Frozen checkpoint metadata: iteration `9200`, hands `150,957,634`, `v5.zero`, `v55`, `9slot_v5`
- Official policy intended: greedy
- Stage intended: `quick5k`, 5,000 Slumbot hands

## Incident

The cadence watcher launched `quick5k_150M` at `2026-07-06T17:08:11Z`.
Four `play_slumbot.py` child sessions were still alive after more than 35 minutes:

- PID `26952`, part1
- PID `48180`, part2
- PID `36972`, part3
- PID `41992`, part4

All four part hand JSONL and dump JSONL files remained `0` bytes, so this run had no
successful Slumbot hands and must not be scored or used for strength claims.

`py-spy dump` showed the children inside Slumbot HTTPS calls, not inside model inference:

- PID `26952`: `requests.post` -> `act()` / `new_hand()` -> SSL connect
- PID `48180`: `requests.post` -> `new_hand()` -> SSL connect
- PID `36972`: `requests.post` -> `act()` -> SSL connect
- PID `41992`: `requests.post` -> `act()` -> SSL connect

Network probes from the same machine succeeded quickly:

- `GET https://slumbot.com/`: about `0.46s`
- `POST https://slumbot.com/slumbot/api/new_hand`: about `0.50s`, response contained
  `action`, `board`, `client_pos`, `hole_cards`, `old_action`, and `token`

Conclusion: the original 4-way benchmark launch entered a bad Slumbot HTTPS/session state.
It is incomplete evidence. Preserve the zero-byte artifacts and status files for audit, but
do not count the run.

## Remediation And Final Outcome

Stop only the stalled Slumbot eval process tree, not the live trainer. Preserve all existing
artifacts in place. Relaunch a replacement quick5k against the same frozen checkpoint using
a new tag:

`v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_150M_quick5k_cadence_rerun1`

First replacement settings:

- checkpoint: original frozen 9200/150.96M cadence checkpoint
- stage: `quick5k`
- policy: greedy
- hands: `1 x 5000` sessions/hands-per-session to reduce Slumbot connection concurrency
- output: preserve full hand JSONL, dump JSONL, CI, promotion gate, dump analysis, loss
  report, artifact audit, hand review, and selector replay if the watcher completes

The first replacement (`rerun1`) also stalled inside the watcher/wrapper child with `0`
hand rows and was stopped. A direct `play_slumbot.py` single-session test (`direct1`)
proved that hand logging worked without wrapper stdout/stderr redirection, but it was slow
and was stopped at `257` partial diagnostic hands.

The completed replacement is:

`v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_150M_quick5k_cadence_direct4`

Final completed replacement settings:

- checkpoint: original frozen 9200/150.96M cadence checkpoint
- stage: `quick5k`
- policy: greedy
- hands: `4 x 1250`
- launch path: four direct `play_slumbot.py` processes, no wrapper stdout/stderr redirection
- full bundle produced: hand JSONL, dump JSONL, CI summary, promotion gate, dump analysis,
  loss report, selector replay, artifact audit, and hand review

Final result:

- hands: `5,000`
- bb/100: `-94.900`
- 95% CI: `[-124.555, -65.246]`
- evidence class: quick screen / L0
- artifact audit: `PASS`
- hand review: `PASS`
- promotion gate: `FAIL`
- selector replay clean: `True`

Loss shape:

- SB/BB: `-95.678` / `-94.123` bb/100
- hero_fold/showdown: `-230.719` / `-26.692` bb/100
- SB open fold/call/raise/all-in: `0.0076` / `0.9780` / `0.0144` / `0.0000`
- BB vs open call/raise: `0.8025` / `0.1161`
- top loss buckets: `sb_open_c`, `bb_vs_open_lt2.5bb_c`, `bb_vs_open_lt2.5bb_f`

This was an eval-cadence repair only. It did not change trainer code, model weights, PPO
settings, action priors, or experiment status. The score is worse than the 100M quick5k
point estimate and still cannot support stronger-than-V4, L5, or L6 claims.
