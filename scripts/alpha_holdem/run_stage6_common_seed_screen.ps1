$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$opponents = @(
    "models/slumbot_imitation_v1_700k_20260725/best.pt",
    "models/slumbot_imitation_seed11b_700k_20260725/best.pt",
    "models/slumbot_imitation_subset_seed22_350k_20260725/best.pt",
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt"
)

$candidates = @(
    @{
        Name = "stage1"
        Checkpoint = "models/slumbot_br_actoronly_500k_20260725/latest.pt"
    },
    @{
        Name = "iter16"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000016_hands000000524732.pt"
    },
    @{
        Name = "iter20"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000020_hands000000655948.pt"
    },
    @{
        Name = "iter24"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000024_hands000000787178.pt"
    },
    @{
        Name = "iter28"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000028_hands000000918335.pt"
    },
    @{
        Name = "iter32"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000032_hands000001049527.pt"
    }
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_stage6_$($candidate.Name)_131k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName"
    & python scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 28 `
        --hands-per-iter 16384 `
        --total-hands 131072 `
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
        --worker-seed-base 2026072562 `
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
