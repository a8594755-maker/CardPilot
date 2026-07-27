$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runDir = 'models\sourcev4_postflop_adapter128_rl_scale10m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Training output already exists: $runDir"
}

& python -X utf8 -u scripts/alpha_holdem/train_v5.py `
    --device cuda `
    --workers 20 `
    --hands-per-iter 32768 `
    --total-hands 10265539 `
    --starting-stack 200 `
    --env-version v55preflopv2v4obs `
    --norm-layer gn `
    --lr 0.00001 `
    --ppo-epochs 2 `
    --ppo-target-kl 0.01 `
    --source-policy-kl-coef 0.5 `
    --policy-postflop-only `
    --separate-preflop-head `
    --postflop-adapter-hidden 128 `
    --adapter-only-training `
    --mini-batch-size 2048 `
    --epsilon 0 `
    --gamma 0.999 `
    --gae-lambda 1.0 `
    --delta1 3 `
    --entropy-coef 0.001 `
    --entropy-floor 0 `
    --k-best 5 `
    --pool-strategy loss-kbest `
    --self-play-fraction 0.25 `
    --opponent-assignment per-iteration `
    --rollout-mode multi `
    --rollout-envs-per-worker 16 `
    --inference-min-batch-slots 128 `
    --inference-batch-deadline-us 1000 `
    --snapshot-every 25 `
    --save-interval 5 `
    --archive-checkpoint-every 25 `
    --run-id sourcev4_postflop_adapter128_rl_scale10m_20260726 `
    --run-dir $runDir `
    --out (Join-Path $runDir 'latest.pt') `
    --seed 20260759 `
    --max-runtime-seconds 21600 `
    --resume models/sourcev4_postflop_adapter128_rl_conservative2m_20260726/latest.pt `
    --allow-resume `
    --reset-optimizer
exit $LASTEXITCODE
