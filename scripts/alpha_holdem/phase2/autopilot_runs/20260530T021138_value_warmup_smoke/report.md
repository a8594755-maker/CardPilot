# Autopilot run: value_warmup_smoke

**Decision**: CONTINUE
**Dry-run**: True
**Reason**: DRY-RUN: would execute; preview next = wire_warmup_ckpt_into_ppo
**Runtime**: 0.0s

## Command
```
python scripts/alpha_holdem/phase2/train_value_warmup.py --anchor-ckpt models/bc/v3_anchor_5M_d1_light/best.pt --rollout-hands 20000 --num-envs 256 --epochs 60 --minibatch-size 1024 --lr 5e-4 --mode value_plus_trunk --policy-kl-coef 30.0 --out models/ppo/warm_critic_autopilot_smoke
```

**Next stage**: wire_warmup_ckpt_into_ppo
**Human approval required**: False