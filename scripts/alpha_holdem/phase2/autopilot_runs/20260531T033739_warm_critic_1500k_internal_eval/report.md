# Autopilot run: warm_critic_1500k_internal_eval

**Decision**: CONTINUE
**Dry-run**: False
**Reason**: all 1 pass-gate(s) ok; advancing to warm_critic_1500k_slumbot_bench
**Runtime**: 2814.4s

## Command
```
python scripts/alpha_holdem/phase2/eval_matrix.py --candidates models/ppo/warm_critic_1500k_scale/final.pt --opponents fold call random heuristic_v3 scripted_aggro scripted_station scripted_jammer pathb10m --hands-quick 20400 --seed 42 --out reports/phase2/warm_critic_1500k_eval
```

## Gates passed
- report_file_exists(reports/phase2/warm_critic_1500k_eval/report.md) = True

**Next stage**: warm_critic_1500k_slumbot_bench
**Human approval required**: False