$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$trainingPid = 27124
while (Get-Process -Id $trainingPid -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 10
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay10m_20260726\latest.pt'
    )
).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $sourceSha -ne
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
) {
    throw 'Standard10 source checkpoint hash mismatch'
}

$stem = 'sourcev4_standard10_position_adapter_rl10m'
$runDir = 'models\sourcev4_standard10_position_adapter_rl10m_20260727'
$candidatePath = Join-Path $runDir 'latest.pt'
$candidate = (Resolve-Path -LiteralPath $candidatePath).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$checkpointSummary = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
    'print(int(c[''total_hands''])); ' +
    'print(int(c.get(''position_adapter_hidden'',0))); ' +
    'print(int(bool(c.get(''position_adapter_only_training'',False))))'
) $candidate)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect position-adapter checkpoint'
}
$totalHands = [int64]$checkpointSummary[-3]
$newTrainingHands = $totalHands - 10283876
if ($newTrainingHands -lt 10000000) {
    throw "Position-adapter run stopped early at $newTrainingHands new hands"
}
if (
    [int]$checkpointSummary[-2] -ne 256 -or
    [int]$checkpointSummary[-1] -ne 1
) {
    throw 'Position-adapter checkpoint metadata mismatch'
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Position-adapter checkpoint deployment dry-run failed'
}

$recordPath = Join-Path $runDir 'experiment_record.json'
$freezeTime = (Get-Date).ToUniversalTime().ToString('o')
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The standard10 policy has a persistent BB/SB strength gap because ' +
        'its actor lacks an explicit public seat feature. PPO-trained neural ' +
        'seat residuals can learn position-specific corrections while the ' +
        'entire inherited actor remains frozen.'
    )
    material_change = (
        'Append the public HU seat to the training observation and optimize ' +
        'only two zero-initialized 256-hidden position residual experts plus ' +
        'the critic for 10M mixed-opponent environment hands.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    new_training_hands = $newTrainingHands
    inherited_lineage_training_hands = 10283876
    inherited_offline_decision_samples = 750000
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = 'SLUMBOT_ASSISTED'
    slumbot_free = $false
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    same_or_earlier_slumbot_hands_forbidden = $true
    candidate_frozen_at = $freezeTime
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    external_result = $null
    status = 'READY_FOR_PURE_FRESH5K'
    recorded_at = $freezeTime
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

# Standard32 already owns a live 20k. Let its exact-hand repair and any
# formal100k launch take precedence over this discovery fresh5k.
$standard32DecisionPath = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay32m_pure_fresh20k_20260726\' +
    'formal100k_decision.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $standard32DecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 10
}
if (-not (Test-Path -LiteralPath $standard32DecisionPath -PathType Leaf)) {
    throw 'Timed out waiting for the Standard32 complete 20k decision'
}
$standard32Decision = Get-Content -LiteralPath $standard32DecisionPath -Raw |
    ConvertFrom-Json
if ([bool]$standard32Decision.launch_formal100k) {
    $formalDir = (
        'models\bench_sourcev4_imitation_anchor_' +
        'mixedselfplay32m_pure_formal100k_20260726'
    )
    while (
        @(
            Get-ChildItem -LiteralPath $formalDir `
                -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
        ).Count -ne 1 -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 20
    }
} else {
    # Give the higher-scale Standard60 watcher time to enter the named bench
    # mutex before this lower-scale architecture discovery screen.
    Start-Sleep -Seconds 20
}

$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Position-adapter fresh5k output already exists: $quickDir"
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
    throw 'Position-adapter fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure position-residual PPO on 40pct self-play plus three learned ' +
        'Slumbot opponents; inherited actor frozen'
    ) `
    -NewTrainingHands $newTrainingHands `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Position-adapter promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Position-adapter fresh5k did not produce one CI summary'
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
