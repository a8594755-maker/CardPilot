$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$mediumReport = (
    'models\sourcev4_heroawr_bbpreflop_awr_medium_20260726\report.json'
)
$deadline = (Get-Date).AddHours(3)
while (
    -not (Test-Path -LiteralPath $mediumReport -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $mediumReport -PathType Leaf)) {
    throw 'Timed out waiting for medium-AWR GPU training to finish'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\' +
        'latest.pt'
    )
).Path
$outputDir = (
    'models\sourcev4_slumbot_history500k_postflop_imitation_' +
    'fullnet_20260726'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "Full-network Slumbot imitation output already exists: $outputDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 1 `
    --street-max 3 `
    --max-rows 500000 `
    --min-rows 50000 `
    --seed 20260809 `
    --device cuda `
    --epochs 8 `
    --batch-size 4096 `
    --lr 0.0001 `
    --kl-coef 0.01 `
    --return-clip-bb 0 `
    --val-fraction 0.05
if ($LASTEXITCODE -ne 0) {
    throw 'Full-network Slumbot postflop imitation training failed'
}

$reportPath = Join-Path $outputDir 'report.json'
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
$oldAccuracy = 0.7081410535481062
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
$retain = $bestAccuracy -gt $oldAccuracy
$bestCheckpoint = (Resolve-Path -LiteralPath $report.best_checkpoint).Path

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'Full-network postflop imitation has enough capacity to model Slumbot ' +
        'raises and non-call actions better than the adapter-only opponent.'
    )
    material_change = (
        'All compatible policy/trunk weights are trained for eight epochs on ' +
        'the same historical postflop Slumbot corpus; no adapter-only freeze.'
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
    old_adapter_validation_accuracy = $oldAccuracy
    candidate_validation_accuracy = $bestAccuracy
    candidate_checkpoint = $bestCheckpoint
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $bestCheckpoint -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    external_result = $null
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
