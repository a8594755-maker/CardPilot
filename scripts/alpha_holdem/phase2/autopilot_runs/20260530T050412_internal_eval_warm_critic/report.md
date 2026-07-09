# Autopilot run: internal_eval_warm_critic

**Decision**: ERROR
**Dry-run**: False
**Reason**: command exited 1; see C:\Users\a8594\CardPilot\scripts\alpha_holdem\phase2\autopilot_runs\20260530T050412_internal_eval_warm_critic\stderr.log
**Runtime**: 4.2s

## Command
```
python scripts/alpha_holdem/phase2/eval_matrix.py --candidates anchor:models/ppo/warm_critic_500k_smoke/final.pt --opponents fold call random heuristic_v3 scripted_aggro scripted_station scripted_jammer pathb10m --hands-quick 20400 --seed 42 --out reports/phase2/warm_critic_500k_eval
```

**Human approval required**: False