$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# The full 20M BR window is long.  Screen its immutable iter500 archive
# (~6.1M new hands) so weak external behavior can be rejected without waiting
# for the endpoint, while the trainer continues unchanged.
$checkpoint = (
    'models\sourcev4_standard10_scaledopponent_bestresponse20m_20260727\' +
    'checkpoints\checkpoint_iter000500_hands*.pt'
)
$deadline = [datetime]'2026-08-01T23:30:00'
$matches = @()
while ($matches.Count -ne 1 -and (Get-Date) -lt $deadline) {
    $matches = @(Get-ChildItem -Path $checkpoint -File -ErrorAction SilentlyContinue)
    if ($matches.Count -eq 0) {
        Start-Sleep -Seconds 20
    } elseif ($matches.Count -gt 1) {
        throw 'More than one scaled-opponent BR iter500 checkpoint exists'
    }
}
if ($matches.Count -ne 1) {
    throw 'Timed out waiting for scaled-opponent BR iter500 checkpoint'
}
$candidate = $matches[0].FullName
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$checkpointValues = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
    'print(int(c[''total_hands''])); print(int(c[''iteration'']))'
) $candidate)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect scaled-opponent BR iter500 checkpoint'
}
$totalHands = [int64]$checkpointValues[-2]
$iteration = [int]$checkpointValues[-1]
$newTrainingHands = $totalHands - 10283876
if ($iteration -ne 500 -or $newTrainingHands -lt 5000000) {
    throw (
        "Unexpected scaled-opponent checkpoint: iter=$iteration " +
        "new_hands=$newTrainingHands"
    )
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Scaled-opponent BR iter500 deployment dry-run failed'
}

$stem = 'sourcev4_standard10_scaledopponent_br_iter500'
$recordDir = Join-Path 'models' "${stem}_20260727"
if (Test-Path -LiteralPath $recordDir) {
    throw "Scaled-opponent BR iter500 record already exists: $recordDir"
}
New-Item -ItemType Directory -Path $recordDir | Out-Null
$freezeTime = $matches[0].LastWriteTimeUtc.ToString('o')
$recordPath = Join-Path $recordDir 'experiment_record.json'
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A Standard10 actor trained against the stronger scale1p25m imitation ' +
        'opponent should adapt to Slumbot-like pressure before the full 20M ' +
        'training endpoint.'
    )
    material_change = (
        'Immutable iter500 archive from the unchanged scaled-opponent BR run; ' +
        'about 6.1M new PPO environment hands from frozen Standard10.'
    )
    source_checkpoint_sha256 = (
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
    )
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    candidate_frozen_at = $freezeTime
    checkpoint_iteration = $iteration
    new_training_hands = $newTrainingHands
    inherited_lineage_training_hands = 10283876
    inherited_offline_decision_samples = 750000
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = (
        'SLUMBOT_ASSISTED_WITH_EVAL_CONTAMINATED_OPPONENT'
    )
    slumbot_free = $false
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    same_or_earlier_slumbot_hands_forbidden = $true
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    external_result = $null
    status = 'READY_FOR_PURE_FRESH5K_ON_NEW_HANDS_ONLY'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Scaled-opponent BR iter500 fresh5k already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    candidate_checkpoint_sha256 = $candidateSha
    candidate_frozen_at = $freezeTime
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    pre_freeze_slumbot_hands_forbidden = $true
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
    throw 'Scaled-opponent BR iter500 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure PPO against scale1p25m/BBweighted/base Slumbot-imitation ' +
        'opponents; evaluation uses only post-freeze fresh hands'
    ) `
    -NewTrainingHands $newTrainingHands `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Scaled-opponent BR iter500 promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Scaled-opponent BR iter500 did not produce one CI summary'
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
