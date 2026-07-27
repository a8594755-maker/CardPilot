$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$base = "models/slumbot_br_stage4_onpolicy_v3_1m_20260725"
$candidates = @(
    @{ Name = "source"; Checkpoint = "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt" },
    @{ Name = "iter04"; Checkpoint = "$base/checkpoints/checkpoint_iter000004_hands000000131535.pt" },
    @{ Name = "iter08"; Checkpoint = "$base/checkpoints/checkpoint_iter000008_hands000000263045.pt" },
    @{ Name = "iter12"; Checkpoint = "$base/checkpoints/checkpoint_iter000012_hands000000394677.pt" },
    @{ Name = "iter16"; Checkpoint = "$base/checkpoints/checkpoint_iter000016_hands000000526147.pt" },
    @{ Name = "iter20"; Checkpoint = "$base/checkpoints/checkpoint_iter000020_hands000000657359.pt" },
    @{ Name = "iter24"; Checkpoint = "$base/checkpoints/checkpoint_iter000024_hands000000788888.pt" },
    @{ Name = "iter28"; Checkpoint = "$base/checkpoints/checkpoint_iter000028_hands000000920151.pt" },
    @{ Name = "final"; Checkpoint = "$base/latest.pt" }
)
$opponents = @(
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk1_seed48_holdout_300k_20260725/best.pt"
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_onpolicy_v3_holdout_$($candidate.Name)_32k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName checkpoint=$($candidate.Checkpoint)"
    & python -X utf8 -u scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 20 `
        --hands-per-iter 32768 `
        --total-hands 32768 `
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
        --inference-min-batch-slots 96 `
        --inference-batch-deadline-us 2000 `
        --worker-seed-base 2026072595 `
        --fixed-training-deal-stream `
        --save-interval 9999 `
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
