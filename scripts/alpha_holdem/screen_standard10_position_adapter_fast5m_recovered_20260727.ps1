$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runDir = (
    'models\sourcev4_standard10_position_adapter_fast5m_20260727'
)
$recordPath = Join-Path $runDir 'experiment_record.json'
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath $record.candidate_checkpoint).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $candidateSha -ne
        'df7d5216e9cb7f15340421688566245f045e7a6703a101a3b38489e2dfa78263'
) {
    throw 'Recovered fast position-adapter checkpoint hash mismatch'
}

$stem = 'sourcev4_standard10_position_adapter_fast5m'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Recovered fast position-adapter fresh5k already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    candidate_checkpoint_sha256 = $candidateSha
    candidate_frozen_at = [string]$record.candidate_frozen_at
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    pre_freeze_slumbot_hands_forbidden = $true
    recovered_after_post_training_launcher_failure = $true
} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (
        Join-Path $quickDir 'evaluation_isolation.json'
    ) -Encoding UTF8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag "${stem}_pure_fresh5k_20260727" `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Recovered fast position-adapter fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure fast position-residual PPO on 40pct self-play plus three learned ' +
        'Slumbot opponents; inherited actor frozen'
    ) `
    -NewTrainingHands ([int64]$record.new_training_hands) `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Recovered fast position-adapter promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Recovered fast position-adapter fresh5k lacks one CI summary'
}
$summary = Get-Content -LiteralPath $summaryPath[0].FullName -Raw |
    ConvertFrom-Json
$decision = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json
$record.external_result = [ordered]@{
    hands = [int]$summary.hands
    bb_per_100 = [double]$summary.bb_per_100
    ci95_lower = [double]$summary.lower_bound_bb_per_100
    ci95_upper = [double]$summary.upper_bound_bb_per_100
    summary = $summaryPath[0].FullName
}
$record.status = if ([bool]$decision.promote_to_fresh20k) {
    'PROMOTED_TO_FRESH20K'
} else {
    'REJECT_EXTERNAL_FRESH5K'
}
$record.recorded_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
