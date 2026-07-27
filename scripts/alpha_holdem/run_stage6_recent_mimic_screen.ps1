$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$opponent = "models/slumbot_imitation_recent14_seed44_300k_20260725/best.pt"
$candidates = @(
    @{
        Name = "stage1"
        Checkpoint = "models/slumbot_br_actoronly_500k_20260725/latest.pt"
    },
    @{
        Name = "stage6_iter20"
        Checkpoint = "models/slumbot_br_progressive_ranges_stage6_1m_20260725/checkpoints/checkpoint_iter000020_hands000000655948.pt"
    }
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_recentmimic_$($candidate.Name)_131k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName"
    & python scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 24 `
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
        --fixed-opponent-checkpoint $opponent `
        --self-play-fraction 0 `
        --opponent-assignment per-iteration `
        --hero-policy-mode greedy `
        --worker-seed-base 2026072564 `
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
