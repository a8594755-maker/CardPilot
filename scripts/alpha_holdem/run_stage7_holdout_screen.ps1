$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$opponents = @(
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk1_seed48_holdout_300k_20260725/best.pt"
)

$stage7 = "models/slumbot_br_postflop_robust_stage7_1m_20260725/checkpoints"
$candidates = @(
    @{ Name = "stage1"; Checkpoint = "models/slumbot_br_actoronly_500k_20260725/latest.pt" },
    @{ Name = "iter8"; Checkpoint = "$stage7/checkpoint_iter000008_hands000000262324.pt" },
    @{ Name = "iter16"; Checkpoint = "$stage7/checkpoint_iter000016_hands000000524704.pt" },
    @{ Name = "iter20"; Checkpoint = "$stage7/checkpoint_iter000020_hands000000655895.pt" },
    @{ Name = "iter24"; Checkpoint = "$stage7/checkpoint_iter000024_hands000000787109.pt" },
    @{ Name = "iter28"; Checkpoint = "$stage7/checkpoint_iter000028_hands000000918213.pt" },
    @{ Name = "iter32"; Checkpoint = "$stage7/checkpoint_iter000032_hands000001049484.pt" }
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_stage7_holdout_$($candidate.Name)_65k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName"
    & python scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 28 `
        --hands-per-iter 16384 `
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
        --worker-seed-base 2026072572 `
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
