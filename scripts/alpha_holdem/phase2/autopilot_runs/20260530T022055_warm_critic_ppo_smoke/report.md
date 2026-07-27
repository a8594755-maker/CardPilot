# Autopilot run: warm_critic_ppo_smoke

**Decision**: CONTINUE
**Dry-run**: False
**Reason**: all 3 pass-gate(s) ok; advancing to internal_eval_warm_critic
**Runtime**: 9797.4s

## Command
```
python scripts/alpha_holdem/phase2/train_population_ppo.py --anchor-ckpt models/bc/v3_anchor_5M_d1_light/best.pt --warmup-ckpt models/ppo/warm_critic_autopilot_smoke/warmup.pt --opponent-mix "self=0.10,heuristic_v3=0.175,heuristic_v2=0.05,heuristic_v3_1=0.05,scripted_aggro=0.175,scripted_station=0.10,scripted_jammer=0.10,proxy:models/proxy/slumbot_public_v2/best.pt=0.05,pathb10m=0.05,v4_final=0.05,fold=0.034,call=0.033,random=0.033" --rollout-steps 256 --num-envs 256 --ppo-epochs 2 --minibatch-size 1024 --lr 3e-5 --entropy-coef 0.01 --anchor-kl-coef 0.05 --target-kl 0.03 --eps-clip 0.2 --value-coef 0.5 --max-grad-norm 1.0 --gamma 0.999 --gae-lambda 0.95 --total-hands 500000 --hands-per-iter 50000 --checkpoint-at "250000,500000" --out models/ppo/warm_critic_500k_smoke
```

## Gates passed
- extra.final_action_mix.0 (0.5430417060852051 lt 0.92) = True
- extra.final_action_mix.8 (0.0 lt 0.15) = True
- extra.hard_stop_reason (None eq None) = True

**Next stage**: internal_eval_warm_critic
**Human approval required**: False