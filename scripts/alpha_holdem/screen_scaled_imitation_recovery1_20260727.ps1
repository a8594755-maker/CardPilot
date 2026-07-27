$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$teacherDir = (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727'
)
$recordPath = Join-Path $teacherDir 'experiment_record.json'
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$candidate = (
    Resolve-Path -LiteralPath ([string]$record.candidate_checkpoint)
).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($candidateSha -ne [string]$record.candidate_checkpoint_sha256) {
    throw 'Scaled imitation candidate hash mismatch'
}

$stem = 'sourcev4_slumbot_allstreet_imitation_scale1p25m_recovery1'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Scaled imitation recovery output already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
$startedAt = (Get-Date).ToUniversalTime().ToString('o')
@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    training_data_classification = 'SLUMBOT_ASSISTED'
    source_training_evaluation_overlap = $true
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    prior_incomplete_output = (
        'C:\Users\a8594\CardPilot\models\' +
        'bench_sourcev4_slumbot_allstreet_imitation_' +
        'scale1p25m_pure_fresh5k_20260727'
    )
    prior_incomplete_hands_reused = $false
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    started_at = $startedAt
} | ConvertTo-Json -Depth 6 |
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
    throw 'Scaled imitation recovery fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure full-network behavior cloning on 1.25M historical Slumbot ' +
        'decisions; evaluated only on new post-freeze hands'
    ) `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 262472 `
    -OfflineDecisionSamples 1250000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Scaled imitation recovery promotion workflow failed'
}

$summaries = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaries.Count -ne 1) {
    throw 'Scaled imitation recovery did not produce one summary'
}
$summary = Get-Content -LiteralPath $summaries[0].FullName -Raw |
    ConvertFrom-Json
$decision = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json

$record | Add-Member -Force -NotePropertyName external_result `
    -NotePropertyValue ([pscustomobject][ordered]@{
        stage = 'fresh5k_recovery1'
        hands = [int]$summary.hands
        bb_per_100 = [double]$summary.bb_per_100
        ci95_lower = [double]$summary.lower_bound_bb_per_100
        ci95_upper = [double]$summary.upper_bound_bb_per_100
        fresh_post_freeze_only = $true
        summary = $summaries[0].FullName
    })
$record | Add-Member -Force -NotePropertyName external_policy_decision `
    -NotePropertyValue (
        if ([bool]$decision.promote_to_fresh20k) {
            'PROMOTED_TO_FRESH20K'
        } else {
            'REJECT_EXTERNAL_FRESH5K'
        }
    )
$record.recorded_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
