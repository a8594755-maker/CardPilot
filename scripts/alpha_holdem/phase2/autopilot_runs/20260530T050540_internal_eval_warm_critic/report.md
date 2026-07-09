# Autopilot run: internal_eval_warm_critic

**Decision**: CONTINUE
**Dry-run**: False
**Reason**: all 1 pass-gate(s) ok; advancing to ask_user_for_rl2_5M
**Runtime**: 801.4s

## Command
```
python scripts/alpha_holdem/phase2/eval_matrix.py --candidates models/ppo/warm_critic_500k_smoke/final.pt --opponents fold call random heuristic_v3 scripted_aggro scripted_station scripted_jammer pathb10m --hands-quick 20400 --seed 42 --out reports/phase2/warm_critic_500k_eval
```

## Gates passed
- report_file_exists(reports/phase2/warm_critic_500k_eval/report.md) = True

**Next stage**: ask_user_for_rl2_5M
**Human approval required**: False