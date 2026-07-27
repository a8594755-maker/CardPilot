$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Reuse the first GPU slot released by the specialist-mixed 60M endpoint for
# one short, diverse pure-weight experiment before returning it to long RL.
$slotMarker = (
    'models\sourcev4_imitation_anchor_' +
    'specialist_mixed40m_from20m_20260726\experiment_record.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $slotMarker -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $slotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the specialist-mixed 60M GPU slot'
}

$sourceRecord = Get-Content -LiteralPath (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726\experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Scaled imitation source hash mismatch'
}

$outputDir = (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "Scaled imitation output already exists: $outputDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '__NO_DUMP_PATH_MATCH_20260727__' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 0 `
    --street-max 3 `
    --max-rows 1250000 `
    --min-rows 750000 `
    --seed 20260842 `
    --device cuda `
    --epochs 12 `
    --batch-size 4096 `
    --lr 0.00005 `
    --kl-coef 0.02 `
    --return-clip-bb 0 `
    --val-fraction 0.05
if ($LASTEXITCODE -ne 0) {
    throw 'Scaled all-street Slumbot imitation training failed'
}

$report = Get-Content -LiteralPath (
    Join-Path $outputDir 'report.json'
) -Raw | ConvertFrom-Json
$bestEpoch = @(
    $report.history |
        Where-Object {
            [int]$_.epoch -eq [int]$report.best_epoch
        }
)[0]
$bestAccuracy = [double]$bestEpoch.behavior_accuracy
$candidate = (Resolve-Path -LiteralPath $report.best_checkpoint).Path
$p0Preflop = [double]$bestEpoch.slice_accuracy.p0s0
$p1Preflop = [double]$bestEpoch.slice_accuracy.p1s0
$mappedRows = [int64]$report.ingest.mapped_rows
$sampledRows = [int64]$report.ingest.sampled_rows

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The first all-street Slumbot imitation model was still improving at ' +
        'epoch 10 and discarded mapped rows; using all newly available ' +
        'opponent decisions at a lower learning rate should improve fidelity.'
    )
    material_change = (
        'Continue pure full-network behavior cloning from the prior best model ' +
        'on up to 1.25M mapped Slumbot-opponent decisions from all available ' +
        'dates for 12 epochs at lr=5e-5 and KL=0.02.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = 0
    inherited_lineage_training_hands = (
        [int64]$sourceRecord.inherited_lineage_training_hands
    )
    offline_decision_samples = $sampledRows
    available_mapped_decision_rows = $mappedRows
    source_validation_accuracy = (
        [double]$sourceRecord.candidate_validation_accuracy
    )
    candidate_validation_accuracy = $bestAccuracy
    candidate_p0_preflop_validation_accuracy = $p0Preflop
    candidate_p1_preflop_validation_accuracy = $p1Preflop
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    decision = if (
        $bestAccuracy -ge
            [double]$sourceRecord.candidate_validation_accuracy -and
        $p0Preflop -ge 0.55 -and
        $p1Preflop -ge 0.70
    ) {
        'READY_FOR_PURE_FRESH5K'
    } else {
        'REJECT'
    }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $outputDir 'experiment_record.json') `
        -Encoding UTF8

# Use the same short-experiment slot for a position-teacher distillation whose
# completed-20k BB gate will be available by now.  This produces one deployable
# network; it never uses the evaluator's seat_hybrid strategy.
$positionRecord = (
    'models\sourcev4_position_teacher_' +
    'standardSB_bbweight3BB_20260727\experiment_record.json'
)
if (-not (Test-Path -LiteralPath $positionRecord -PathType Leaf)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/run_position_teacher_distill_20260727.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Position-teacher distillation pipeline failed'
    }
}

# Use the released slot for a conservative standard10 best response only if
# the larger opponent model actually improved held-out fidelity.
$scaledExperiment = Get-Content -LiteralPath (
    Join-Path $outputDir 'experiment_record.json'
) -Raw | ConvertFrom-Json
if ([string]$scaledExperiment.decision -eq 'READY_FOR_PURE_FRESH5K') {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/run_scaled_opponent_bestresponse20m_20260727.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Scaled-opponent best-response pipeline failed'
    }
} else {
    Write-Output (
        'Scaled opponent failed held-out fidelity; best-response run skipped.'
    )
}

# After the independent best-response run, reuse the slot for specialist250
# only if its frozen 60M external gate actually permits continuation.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/continue_imitation_lineage_to250m_20260727.ps1' `
    -Lineage 'specialist-mixed'
exit $LASTEXITCODE
