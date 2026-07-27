$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$base = "models/slumbot_br_mcgae_v12_524k_20260725"
$candidates = @(
    @{ Name = "source"; Checkpoint = "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt" },
    @{ Name = "iter2"; Checkpoint = "$base/checkpoints/checkpoint_iter000002_hands000000065561.pt" },
    @{ Name = "iter4"; Checkpoint = "$base/checkpoints/checkpoint_iter000004_hands000000131340.pt" },
    @{ Name = "iter6"; Checkpoint = "$base/checkpoints/checkpoint_iter000006_hands000000197019.pt" },
    @{ Name = "iter8"; Checkpoint = "$base/checkpoints/checkpoint_iter000008_hands000000262700.pt" },
    @{ Name = "iter12"; Checkpoint = "$base/checkpoints/checkpoint_iter000012_hands000000394492.pt" },
    @{ Name = "iter16"; Checkpoint = "$base/latest.pt" }
)
$opponents = @(
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk1_seed48_holdout_300k_20260725/best.pt"
)

foreach ($candidate in $candidates) {
    $runName = "localgreedy_mcgae_v12_holdout_$($candidate.Name)_65k_20260725"
    $runDir = "models/$runName"
    Write-Output "START $runName"
    & python -X utf8 -u scripts/alpha_holdem/train_v5.py `
        --device cuda `
        --workers 28 `
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
        --inference-min-batch-slots 128 `
        --inference-batch-deadline-us 2000 `
        --worker-seed-base 2026072588 `
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
