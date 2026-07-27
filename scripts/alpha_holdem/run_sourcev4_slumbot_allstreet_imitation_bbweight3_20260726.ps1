$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Keep at most two concurrent GPU optimizers.  The standard 10M trainer writes
# this record as soon as its GPU work is complete, before its CPU-only screen.
$gpuSlotMarker = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay10m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(2)
while (
    -not (Test-Path -LiteralPath $gpuSlotMarker -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 15
}
if (-not (Test-Path -LiteralPath $gpuSlotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the standard imitation-anchor GPU slot'
}

$sourceDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726'
)
$sourceRecord = Get-Content -LiteralPath (
    Join-Path $sourceDir 'experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'BB-weighted imitation source hash mismatch'
}

$runDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "BB-weighted imitation output already exists: $runDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $runDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 0 `
    --street-max 3 `
    --max-rows 750000 `
    --min-rows 100000 `
    --seed 20260829 `
    --device cuda `
    --epochs 5 `
    --batch-size 4096 `
    --lr 0.00003 `
    --kl-coef 0.1 `
    --return-clip-bb 0 `
    --position-0-weight 3 `
    --val-fraction 0.05
if ($LASTEXITCODE -ne 0) {
    throw 'BB-weighted all-street imitation training failed'
}

$report = Get-Content -LiteralPath (Join-Path $runDir 'report.json') -Raw |
    ConvertFrom-Json
$ranked = @(
    $report.history |
        ForEach-Object {
            [pscustomobject]@{
                epoch = [int]$_.epoch
                behavior_accuracy = [double]$_.behavior_accuracy
                p0_preflop_accuracy = [double]$_.slice_accuracy.p0s0
                p1_preflop_accuracy = [double]$_.slice_accuracy.p1s0
                minimum_preflop_accuracy = [math]::Min(
                    [double]$_.slice_accuracy.p0s0,
                    [double]$_.slice_accuracy.p1s0
                )
            }
        } |
        Sort-Object `
            @{Expression='p0_preflop_accuracy';Descending=$true},
            @{Expression='behavior_accuracy';Descending=$true}
)
$eligible = @(
    $ranked | Where-Object {
        $_.behavior_accuracy -ge 0.74 -and
        $_.p1_preflop_accuracy -ge 0.70
    }
)
$selected = if ($eligible.Count -gt 0) {
    $eligible[0]
} else {
    @(
        $ranked |
            Sort-Object `
                @{Expression='minimum_preflop_accuracy';Descending=$true},
                @{Expression='behavior_accuracy';Descending=$true}
    )[0]
}
$selectedCheckpoint = (Resolve-Path -LiteralPath (
    Join-Path $runDir "epoch_$($selected.epoch).pt"
)).Path
$selectedCopy = Join-Path $runDir 'selected.pt'
Copy-Item -LiteralPath $selectedCheckpoint -Destination $selectedCopy
$selectedCopy = (Resolve-Path -LiteralPath $selectedCopy).Path

$retain = (
    $selected.behavior_accuracy -ge 0.74 -and
    $selected.p0_preflop_accuracy -ge 0.634 -and
    $selected.p1_preflop_accuracy -ge 0.70
)
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The strongest pure checkpoint is statistically near Slumbot but loses ' +
        'most clearly from the big blind.  Reweighting the same opponent-' +
        'imitation corpus toward position 0 should improve the weakest held-' +
        'out slice without evaluator-side rules.'
    )
    material_change = (
        'Fine-tune every learned weight of the direct all-street Slumbot ' +
        'imitation source for five epochs with BB rows weighted 3x, lr=3e-5 ' +
        'and source KL=0.1.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = 0
    inherited_lineage_training_hands = 262472
    offline_decision_samples = (
        [int64]$report.train_rows + [int64]$report.val_rows
    )
    source_overall_accuracy = 0.75848
    source_p0_preflop_accuracy = 0.6043188829355415
    source_p1_preflop_accuracy = 0.7731904690543984
    selected_epoch = $selected.epoch
    selected_overall_accuracy = $selected.behavior_accuracy
    selected_p0_preflop_accuracy = $selected.p0_preflop_accuracy
    selected_p1_preflop_accuracy = $selected.p1_preflop_accuracy
    selected_checkpoint = $selectedCopy
    selected_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $selectedCopy -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    retention_rule = (
        'overall accuracy >= 0.74, P0 preflop accuracy >= 0.634, and P1 ' +
        'preflop accuracy >= 0.70'
    )
    decision = if ($retain) { 'READY_FOR_PURE_FRESH5K' } else { 'REJECT' }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
exit 0
