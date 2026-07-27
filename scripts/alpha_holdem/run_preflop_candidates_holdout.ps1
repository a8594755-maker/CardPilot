$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$v14base = "models/alpha_holdem_v5_from_zero/slumbot_br_preflop_teacher_v14b_262k_20260725/checkpoints"
$candidates = @(
    @{
        Name = "v14b_iter4"
        Checkpoint = "$v14base/checkpoint_iter000004_hands000000131253.pt"
    },
    @{
        Name = "v14b_iter8"
        Checkpoint = "models/slumbot_br_preflop_teacher_v14b_262k_20260725/latest.pt"
    },
    @{
        Name = "v16_exactpostflop_iter8"
        Checkpoint = "models/slumbot_br_preflop_teacher_v16_exactpostflop_262k_20260725/latest.pt"
    }
)
$opponents = @(
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk1_seed48_holdout_300k_20260725/best.pt"
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_preflop_$($candidate.Name)_65k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName"
    & python -X utf8 -u scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 20 `
        --hands-per-iter 32768 `
        --total-hands 65536 `
        --env-version v55v4obs `
        --norm-layer gn `
        --lr 0 `
        --ppo-epochs 1 `
        --ppo-target-kl 0 `
        --value-coef 0 `
        --entropy-coef 0 `
        --entropy-floor 0 `
        --fixed-opponent-checkpoints @opponents `
        --self-play-fraction 0 `
        --opponent-assignment per-iteration `
        --hero-policy-mode greedy `
        --rollout-mode multi `
        --rollout-envs-per-worker 16 `
        --inference-min-batch-slots 160 `
        --inference-batch-deadline-us 2000 `
        --worker-seed-base 2026072588 `
        --fixed-training-deal-stream `
        --save-interval 9999 `
        --separate-preflop-head `
        --resume $candidate.Checkpoint `
        --allow-resume `
        --reset-optimizer `
        --reset-hand-counter `
        --overwrite `
        --run-dir $runDir `
        --out "$runDir/latest.pt" `
        --run-id $runName
    if ($LASTEXITCODE -ne 0) {
        throw "$runName failed with exit code $LASTEXITCODE"
    }
    Write-Output "DONE $runName"
}
