# AlphaHoldem V5 Takeover Handoff - 2026-07-06 12:08 EDT

Scope: AlphaHoldem V5-from-zero Slumbot track in `C:\Users\a8594\CardPilot`.

## Active Run

- run_id: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- run_dir: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- trainer PID: `56876`, responding at last check; it was not stopped or restarted.
- latest direct train tail: iter/hands `9074` / `148,890,209`, h/s `682`.
- latest queue snapshot checked at `2026-07-06T16:07:01Z`: checkpoint iter/hands `9000` / `147,675,855`; live iter/hands `9070` / `148,824,552`; health `PASS`; recommendation `Wait for gate_9100`.

## EXP-001 Status

EXP-001 mirrored-deal internal eval is adopted as of this handoff. It remains an internal-only measuring stick and cannot support Slumbot/L5/L6 strength claims.

Artifacts:

- `scripts\alpha_holdem\v5_mirror_eval.py`
- `<run_dir>\v5_mirror_eval_exp001_500p.json/md`
- `<run_dir>\v5_mirror_eval_exp001_10kp.json/md`
- `<run_dir>\v5_mirror_eval_exp001_priorv5_25kp.json/md`

Validated:

- `python -m py_compile scripts\alpha_holdem\v5_mirror_eval.py`
- JSON parsed with `python -m json.tool`
- self-vs-self mirrored smoke: `0.0 bb/100`
- eval stderr logs were empty

Adopted gate evidence:

- active 9000 vs V4 final: `-92.02 bb/100 +/-13.31`, `10,000` mirrored pairs
- active 9000 vs prior V5 59M: `+27.98 bb/100 +/-18.61`, `25,000` mirrored pairs

Interpretation:

- V4 anchor direction is worse than V4, consistent with official Slumbot evidence still not proving V5 stronger than V4.
- Prior-V5 anchor is positive on the internal mirrored eval, with CI now below `+/-20`; use it as a progress signal for EXP-002+ gates, not as a strength claim.

## Official Slumbot

- latest official greedy Slumbot evidence: 100M quick5k, `5,000` hands, `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, evidence class `quick_screen`, L0.
- trend remains `SLUMBOT_POINT_ESTIMATE_DOWN`; no stronger-than-V4, L5, or L6 claim is allowed.
- latest loss shape: SB/BB `-115.046` / `-55.028`; hero_fold/showdown `-167.737` / `-10.629`; top preflop loss buckets `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`.
- analysis coverage: `WARN_HISTORICAL_INCOMPLETE`, complete/total `6/7`; only 50M remains incomplete due missing decision dumps.

## Latest Gate/Post-Gate

- latest completed gate: `gate_9000`, PASS, checkpoint iter/hands `9000` / `147,675,855`.
- latest completed post-gate review: `v5_post_gate_review_9000.json`, `REVIEW_REQUIRED_NO_AUTO_RESTART`.
- internal probe 9000: `REGRESSION_RISK_INTERNAL`, delta mean/lower `-82.500` / `-107.725`; use as a watch signal only.
- preflop probe: `WARN`, warning_count `2`.

## Next Action

Wait for `gate_9100`, then refresh/read `v5_post_gate_review_9100.json/md`. Do not launch EXP-002 cutover until gate-boundary procedure and playbook lifecycle allow it. The next external Slumbot screen is `quick5k_150M`, waiting for checkpoint hands >= `150,000,000`.

