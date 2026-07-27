$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay10m_20260726\latest.pt'
    )
).Path
$expectedSourceSha = (
    '91b0c587a5a76e9a8f38217e0b304136' +
    'ef298118a99b69cc743899fc4b16e428'
)
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne $expectedSourceSha) {
    throw 'Standard10 source hash mismatch'
}

$evidenceDir = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay10m_pure_fresh20k_20260726'
)
$summaries = @(
    Get-ChildItem -LiteralPath $evidenceDir -Filter '*_ci_summary.json' -File
)
if ($summaries.Count -ne 1) {
    throw 'Standard10 fresh20k evidence must contain exactly one CI summary'
}
$summary = Get-Content -LiteralPath $summaries[0].FullName -Raw |
    ConvertFrom-Json
if ([int]$summary.hands -ne 20000) {
    throw "Expected 20,000 source hands, found $($summary.hands)"
}

$outDir = (
    'models\sourcev4_standard10_bb_position_awr256_' +
    'fresh20k_20260727'
)
$candidatePath = Join-Path $outDir 'best.pt'
$trainingReportPath = Join-Path $outDir 'report.json'
$validationPath = Join-Path $outDir 'candidate_validation.json'
$reuseTraining = $false
if (Test-Path -LiteralPath $outDir) {
    foreach ($requiredPath in @(
        $candidatePath,
        $trainingReportPath,
        $validationPath
    )) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "Incomplete existing position-AWR output: $requiredPath"
        }
    }
    $existingValidation = Get-Content -LiteralPath $validationPath -Raw |
        ConvertFrom-Json
    $existingCandidateSha = (
        Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if (
        [string]$existingValidation.decision -ne
            'READY_FOR_PURE_FRESH5K' -or
        $existingCandidateSha -ne [string]$existingValidation.candidate_sha256
    ) {
        throw 'Existing position-AWR output failed reuse validation'
    }
    $reuseTraining = $true
} else {
    & python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
        --source-checkpoint $source `
        --out-dir $outDir `
        --roots $evidenceDir `
        --exclude-substring '__never_exclude__' `
        --obs-version v4 `
        --actor hero `
        --position 0 `
        --max-rows 100000 `
        --min-rows 20000 `
        --seed 20260851 `
        --device cuda `
        --epochs 6 `
        --batch-size 1024 `
        --lr 0.00002 `
        --weight-decay 0.00001 `
        --kl-coef 10 `
        --return-clip-bb 10 `
        --beta-bb 5 `
        --min-bucket-count 30 `
        --weight-min 0.1 `
        --weight-max 4 `
        --decision-risk-power 0.25 `
        --decision-risk-cap 2 `
        --position-adapter-hidden 256 `
        --position-policy-adapter-only
    if ($LASTEXITCODE -ne 0) {
        throw 'Standard10 BB position-AWR training failed'
    }
}

$candidate = (Resolve-Path -LiteralPath $candidatePath).Path
$trainingReport = (
    Resolve-Path -LiteralPath $trainingReportPath
).Path
if (-not $reuseTraining) {
    & python -X utf8 scripts/alpha_holdem/validate_position_awr_candidate.py `
        --source $source `
        --candidate $candidate `
        --training-report $trainingReport `
        --out $validationPath `
        --max-source-kl 0.02
    if ($LASTEXITCODE -ne 0) {
        throw 'Standard10 BB position-AWR candidate failed the internal gate'
    }
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Standard10 BB position-AWR deployment dry-run failed'
}

$stem = 'sourcev4_standard10_bb_position_awr256_fresh20k'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    $existingQuickArtifacts = @(
        Get-ChildItem -LiteralPath $quickDir -Force
    )
    if ($existingQuickArtifacts.Count -ne 0) {
        throw "Position-AWR fresh5k output already exists: $quickDir"
    }
} else {
    New-Item -ItemType Directory -Path $quickDir | Out-Null
}
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
    throw 'Standard10 BB position-AWR fresh5k failed'
}

$report = Get-Content -LiteralPath $trainingReport -Raw | ConvertFrom-Json
$offlineDecisionSamples = (
    [int64]$report.train_rows + [int64]$report.val_rows
)
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_standard10_bb_position_awr256_fresh20k' `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure BB-only position residual AWR on the source policy fresh20k; ' +
        'SB output remains exactly source'
    ) `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples $offlineDecisionSamples
if ($LASTEXITCODE -ne 0) {
    throw 'Standard10 BB position-AWR promotion workflow failed'
}

$quickSummary = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($quickSummary.Count -ne 1) {
    throw 'Position-AWR fresh5k did not produce exactly one CI summary'
}
$quickDecision = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json
$experiment = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The strongest completed standard10 policy loses mainly from the BB. ' +
        'A conservative outcome-weighted BB-only neural residual can improve ' +
        'that seat while leaving every inherited tensor and the SB residual ' +
        'exactly unchanged.'
    )
    material_change = (
        'Add a zero-initialized 256-hidden position residual and optimize only ' +
        'its BB branch on 20,000 fresh source-policy Slumbot hands using ' +
        'clipped AWR, a strong source KL penalty and bounded risk weighting.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    source_external_hands = 20000
    source_external_bb_per_100 = [double]$summary.bb_per_100
    new_training_hands = 0
    inherited_lineage_training_hands = 10283876
    offline_decision_samples = $offlineDecisionSamples
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    validation = (Resolve-Path -LiteralPath $validationPath).Path
    external_result = [ordered]@{
        evaluation = 'greedy-direct fresh5k'
        hands = [int]$quickDecision.quick5k_hands
        summary = $quickSummary[0].FullName
        bb_per_100 = [double]$quickDecision.quick5k_bb_per_100
        ci95_lower = [double]$quickDecision.quick5k_ci95_lower
        ci95_upper = [double]$quickDecision.quick5k_ci95_upper
    }
    decision = (
        if ([bool]$quickDecision.promote_to_fresh20k) {
            'PROMOTED_TO_FRESH20K'
        } else {
            'REJECT_EXTERNAL_FRESH5K'
        }
    )
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$experiment | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $outDir 'experiment_record.json') `
        -Encoding UTF8
