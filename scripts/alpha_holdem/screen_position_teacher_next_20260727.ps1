$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$recordPath = (
    'models\sourcev4_position_teacher_' +
    'standardSB_bbweight3BB_20260727\experiment_record.json'
)
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if ([string]$record.decision -ne 'READY_FOR_PURE_FRESH5K') {
    throw "Position-teacher candidate is not ready: $($record.decision)"
}
if (
    -not [bool]$record.pure_weight_policy -or
    [bool]$record.evaluator_side_overrides
) {
    throw 'Position-teacher candidate violates the pure-weight contract'
}
$checkpoint = (
    Resolve-Path -LiteralPath $record.candidate_checkpoint
).Path
$sha = (
    Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sha -ne [string]$record.candidate_checkpoint_sha256) {
    throw 'Position-teacher checkpoint hash mismatch'
}

$stem = 'sourcev4_position_teacher_standardSB_bbweight3BB'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Position-teacher fresh5k output already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null

# bench_v55_slumbot owns the named single-evaluation mutex. Starting this
# launcher now reserves the next external slot while the current legacy bench
# completes, without overlapping any play_slumbot workers.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint `
    -Tag "${stem}_pure_fresh5k_20260727" `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Position-teacher fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_position_teacher_standardSB_bbweight3BB' `
    -QuickDir $quickDir `
    -SourcePolicy $checkpoint `
    -OutputStem $stem `
    -TrainingMethod 'pure-position-teacher-dual-expert-distillation' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands (
        [int64]$record.inherited_lineage_training_hands
    ) `
    -OfflineDecisionSamples ([int64]$record.offline_decision_samples) `
    -DeferFormal
exit $LASTEXITCODE
