$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Avoid adding a fourth simultaneous GPU optimizer.  The conservative
# full-network RL endpoint writes its record after training and fixed probes,
# at which point its GPU slot is free and its external screen is CPU-only.
$gpuSlotMarker = (
    'models\sourcev4_heroawr_slumbot_mimicv2_' +
    'fullnet_conservative2m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(4)
while (
    -not (Test-Path -LiteralPath $gpuSlotMarker -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $gpuSlotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the conservative full-network GPU slot'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_' +
        '20260725\latest.pt'
    )
).Path
$outputDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "All-street Slumbot imitation output already exists: $outputDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 0 `
    --street-max 3 `
    --max-rows 750000 `
    --min-rows 100000 `
    --seed 20260819 `
    --device cuda `
    --epochs 10 `
    --batch-size 4096 `
    --lr 0.0001 `
    --kl-coef 0.01 `
    --return-clip-bb 0 `
    --val-fraction 0.05
if ($LASTEXITCODE -ne 0) {
    throw 'Full-network Slumbot all-street imitation training failed'
}

$reportPath = Join-Path $outputDir 'report.json'
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
$bestEpoch = @(
    $report.history |
        Where-Object {
            (
                $null -ne $report.best_epoch -and
                [int]$_.epoch -eq [int]$report.best_epoch
            ) -or (
                $null -eq $report.best_epoch -and
                [math]::Abs(
                    [double]$_.behavior_accuracy -
                    [double]$report.best_selection_value
                ) -lt 1e-12
            )
        }
)[0]
$bestAccuracy = [double]$bestEpoch.behavior_accuracy
$p0PreflopAccuracy = [double]$bestEpoch.slice_accuracy.p0s0
$p1PreflopAccuracy = [double]$bestEpoch.slice_accuracy.p1s0
$preflopMinAccuracy = [math]::Min(
    $p0PreflopAccuracy,
    $p1PreflopAccuracy
)
$retain = (
    $bestAccuracy -ge 0.70 -and
    $preflopMinAccuracy -ge 0.50
)
$bestCheckpoint = (Resolve-Path -LiteralPath $report.best_checkpoint).Path

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A single full-network all-street opponent model can remove the ' +
        'preflop fidelity hole in the current mimic-v2 league while retaining ' +
        'the stronger postflop imitation capacity.'
    )
    material_change = (
        'Train all compatible trunk and policy weights for ten epochs on the ' +
        'historical Slumbot opponent decisions from every street.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = 0
    inherited_lineage_training_hands = 262472
    offline_decision_samples = (
        [int64]$report.train_rows + [int64]$report.val_rows
    )
    old_allstreet_adapter_validation_accuracy = 0.52808
    candidate_validation_accuracy = $bestAccuracy
    candidate_p0_preflop_validation_accuracy = $p0PreflopAccuracy
    candidate_p1_preflop_validation_accuracy = $p1PreflopAccuracy
    candidate_preflop_min_validation_accuracy = $preflopMinAccuracy
    retention_rule = (
        'overall held-out behavior accuracy >= 0.70 and both preflop ' +
        'position accuracies >= 0.50'
    )
    candidate_checkpoint = $bestCheckpoint
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $bestCheckpoint -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    external_result = $null
    intended_use = 'TRAINING_OPPONENT_ONLY'
    decision = if ($retain) {
        'RETAIN_AS_TRAINING_OPPONENT'
    } else {
        'REJECT'
    }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $outputDir 'experiment_record.json') `
        -Encoding UTF8
exit 0
