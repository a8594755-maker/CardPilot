$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$outputDir = (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727'
)
$reportPath = Join-Path $outputDir 'report.json'
$recordPath = Join-Path $outputDir 'experiment_record.json'
$deadline = [datetime]'2026-08-01T23:30:00'
foreach ($path in @($reportPath, $recordPath)) {
    while (
        -not (Test-Path -LiteralPath $path -PathType Leaf) -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 10
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Timed out waiting for $path"
    }
}

$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
if ([string]$record.decision -eq 'READY_FOR_PURE_FRESH5K') {
    Write-Output (
        'Active wrapper already selected an eligible scaled checkpoint; ' +
        'recovery and duplicate best-response launch skipped.'
    )
    exit 0
}
$sourceRecord = Get-Content -LiteralPath (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726\experiment_record.json'
) -Raw | ConvertFrom-Json
$sourceAccuracy = [double]$sourceRecord.candidate_validation_accuracy
$eligibleEpochs = @(
    $report.history |
        Where-Object {
            [double]$_.behavior_accuracy -ge $sourceAccuracy -and
            [double]$_.slice_accuracy.p0s0 -ge 0.55 -and
            [double]$_.slice_accuracy.p1s0 -ge 0.70
        } |
        Sort-Object {
            [double]$_.validation_objective
        }
)
if ($eligibleEpochs.Count -eq 0) {
    Write-Output 'No scaled-imitation epoch satisfies all held-out gates.'
    exit 0
}

$selected = $eligibleEpochs[0]
$epochNumber = [int]$selected.epoch
$candidate = (
    Resolve-Path -LiteralPath (
        Join-Path $outputDir "epoch_${epochNumber}.pt"
    )
).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()

# The active wrapper was loaded before constrained selection was added. Repair
# only its compact discovery record; raw checkpoints and training report remain
# untouched.
$corrected = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = [string]$record.hypothesis
    material_change = [string]$record.material_change
    source_checkpoint = [string]$record.source_checkpoint
    source_checkpoint_sha256 = [string]$record.source_checkpoint_sha256
    new_training_hands = [int64]$record.new_training_hands
    inherited_lineage_training_hands = (
        [int64]$record.inherited_lineage_training_hands
    )
    offline_decision_samples = [int64]$report.ingest.sampled_rows
    available_mapped_decision_rows = [int64]$report.ingest.mapped_rows
    source_validation_accuracy = $sourceAccuracy
    unconstrained_best_epoch = [int]$report.best_epoch
    selected_eligible_epoch = $epochNumber
    candidate_validation_accuracy = [double]$selected.behavior_accuracy
    candidate_validation_objective = (
        [double]$selected.validation_objective
    )
    candidate_p0_preflop_validation_accuracy = (
        [double]$selected.slice_accuracy.p0s0
    )
    candidate_p1_preflop_validation_accuracy = (
        [double]$selected.slice_accuracy.p1s0
    )
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    decision = 'READY_FOR_PURE_FRESH5K'
    selection_recovery = (
        'Selected the lowest validation-objective epoch among checkpoints ' +
        'meeting overall and both preflop-slice held-out gates.'
    )
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$corrected | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$bestResponseDir = (
    'models\sourcev4_standard10_scaledopponent_' +
    'bestresponse20m_20260727'
)
if (-not (Test-Path -LiteralPath $bestResponseDir)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/run_scaled_opponent_bestresponse20m_20260727.ps1'
    exit $LASTEXITCODE
}
Write-Output 'Scaled best-response output already exists; launch skipped.'
