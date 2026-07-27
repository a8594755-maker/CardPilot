$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidate = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_standard10_bb_position_awr256_' +
        'fresh20k_20260727\best.pt'
    )
).Path
$expectedCandidateSha = (
    '907207391ec6a4b2864bb497443a86bd' +
    '36ea1863b6674b94ceb07f41de637702'
)
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($candidateSha -ne $expectedCandidateSha) {
    throw 'Position-AWR candidate hash mismatch'
}

$stem = 'sourcev4_standard10_bb_position_awr256_fresh20k'
$tag = "${stem}_pure_fresh5k_20260727"
$quickDir = (
    Resolve-Path -LiteralPath (
        "models\bench_${tag}"
    )
).Path
$repairDir = Join-Path 'models' "bench_${tag}_repair1"

$originalHandFiles = @(
    Get-ChildItem -LiteralPath $quickDir `
        -Filter "bench_v55_${tag}_part*_hands.jsonl" -File |
        Sort-Object Name
)
if ($originalHandFiles.Count -ne 10) {
    throw "Expected 10 original hand files, found $($originalHandFiles.Count)"
}
$originalHands = 0
foreach ($file in $originalHandFiles) {
    $originalHands += (
        Get-Content -LiteralPath $file.FullName | Measure-Object -Line
    ).Lines
}
if ($originalHands -ne 4999) {
    throw "Repair applies only to the preserved 4,999-hand bundle; found $originalHands"
}

if (Test-Path -LiteralPath $repairDir) {
    $existingRepairArtifacts = @(
        Get-ChildItem -LiteralPath $repairDir -Force
    )
    if ($existingRepairArtifacts.Count -ne 0) {
        throw "Non-empty repair output already exists: $repairDir"
    }
} else {
    New-Item -ItemType Directory -Path $repairDir | Out-Null
}

# bench_v55_slumbot.ps1 owns the shared named mutex, so this one-hand repair
# waits behind any active evaluation rather than contending with it.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag "${tag}_repair1" `
    -HandsPerSession 1 `
    -Sessions 1 `
    -OutputDir (Resolve-Path -LiteralPath $repairDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'One-hand position-AWR evidence repair failed'
}

$repairHandFiles = @(
    Get-ChildItem -LiteralPath $repairDir -Filter '*_hands.jsonl' -File
)
$repairDumpFiles = @(
    Get-ChildItem -LiteralPath $repairDir -Filter '*_dump.jsonl' -File
)
$repairLogFiles = @(
    Get-ChildItem -LiteralPath $repairDir -Filter '*.log' -File |
        Where-Object { $_.Name -notmatch '_err\.log$' }
)
if (
    $repairHandFiles.Count -ne 1 -or
    $repairDumpFiles.Count -ne 1 -or
    $repairLogFiles.Count -ne 1
) {
    throw 'One-hand repair did not produce one complete raw evidence triplet'
}
$repairHands = (
    Get-Content -LiteralPath $repairHandFiles[0].FullName |
        Measure-Object -Line
).Lines
if ($repairHands -ne 1) {
    throw "One-hand repair produced $repairHands hands"
}

$derivedArtifacts = @(
    "bench_v55_${tag}_summary.txt",
    "bench_v55_${tag}_ci_summary.json",
    "bench_v55_${tag}_ci_summary.txt",
    "bench_v55_${tag}_promotion_gate.json",
    "bench_v55_${tag}_promotion_gate.md",
    "bench_v55_${tag}_promotion_gate.txt",
    "bench_v55_${tag}_dump_analysis.txt",
    "bench_v55_${tag}_loss_report.json",
    "bench_v55_${tag}_loss_report.md",
    "bench_v55_${tag}_loss_report.txt"
)
foreach ($name in $derivedArtifacts) {
    $sourcePath = Join-Path $quickDir $name
    if (Test-Path -LiteralPath $sourcePath) {
        $preservedPath = "$sourcePath.incomplete4999"
        if (-not (Test-Path -LiteralPath $preservedPath)) {
            Copy-Item -LiteralPath $sourcePath -Destination $preservedPath
        }
    }
}

$allHandFiles = @($originalHandFiles.FullName) + @($repairHandFiles[0].FullName)
$ciSummary = Join-Path $quickDir "bench_v55_${tag}_ci_summary.json"
$ciArgs = @('scripts/alpha_holdem/slumbot_ci_from_hands.py') +
    $allHandFiles + @('--out-json', $ciSummary)
$ciResult = & python -X utf8 @ciArgs 2>&1
$ciExitCode = $LASTEXITCODE
$ciText = $ciResult -join "`n"
$ciText | Out-File -FilePath (
    Join-Path $quickDir "bench_v55_${tag}_ci_summary.txt"
) -Encoding utf8
if ($ciExitCode -ne 0 -or -not (Test-Path -LiteralPath $ciSummary)) {
    throw "Combined 5,000-hand CI rebuild failed: $ciText"
}
$ci = Get-Content -LiteralPath $ciSummary -Raw | ConvertFrom-Json
if ([int]$ci.hands -ne 5000) {
    throw "Combined CI has $($ci.hands) hands instead of 5,000"
}

$promotionJson = Join-Path $quickDir "bench_v55_${tag}_promotion_gate.json"
$promotionMd = Join-Path $quickDir "bench_v55_${tag}_promotion_gate.md"
$promotionResult = & python -X utf8 `
    scripts/alpha_holdem/v5_slumbot_promotion_gate.py `
    --checkpoint $candidate `
    --ci-json $ciSummary `
    --out-json $promotionJson `
    --out-md $promotionMd 2>&1
$promotionExitCode = $LASTEXITCODE
$promotionText = $promotionResult -join "`n"
$promotionText | Out-File -FilePath (
    Join-Path $quickDir "bench_v55_${tag}_promotion_gate.txt"
) -Encoding utf8
if ($promotionExitCode -ne 0 -or -not (Test-Path -LiteralPath $promotionJson)) {
    throw "Combined promotion-gate rebuild failed: $promotionText"
}

$originalDumpFiles = @(
    Get-ChildItem -LiteralPath $quickDir `
        -Filter "bench_v55_${tag}_part*_dump.jsonl" -File |
        Sort-Object Name
)
if ($originalDumpFiles.Count -ne 10) {
    throw "Expected 10 original dump files, found $($originalDumpFiles.Count)"
}
$allDumpFiles = @($originalDumpFiles.FullName) + @($repairDumpFiles[0].FullName)
$dumpResult = & python -X utf8 scripts/alpha_holdem/analyze_dump.py `
    --label $tag `
    --dumps @allDumpFiles 2>&1
$dumpExitCode = $LASTEXITCODE
$dumpText = $dumpResult -join "`n"
$dumpText | Out-File -FilePath (
    Join-Path $quickDir "bench_v55_${tag}_dump_analysis.txt"
) -Encoding utf8
if ($dumpExitCode -ne 0) {
    throw "Combined decision-dump analysis failed: $dumpText"
}

$lossJson = Join-Path $quickDir "bench_v55_${tag}_loss_report.json"
$lossMd = Join-Path $quickDir "bench_v55_${tag}_loss_report.md"
$lossArgs = @(
    'scripts/alpha_holdem/v5_slumbot_loss_report.py',
    '--label', $tag,
    '--dumps'
) + $allDumpFiles + @(
    '--out-json', $lossJson,
    '--out-md', $lossMd
)
$lossResult = & python -X utf8 @lossArgs 2>&1
$lossExitCode = $LASTEXITCODE
$lossText = $lossResult -join "`n"
$lossText | Out-File -FilePath (
    Join-Path $quickDir "bench_v55_${tag}_loss_report.txt"
) -Encoding utf8
if (
    $lossExitCode -ne 0 -or
    -not (Test-Path -LiteralPath $lossJson) -or
    -not (Test-Path -LiteralPath $lossMd)
) {
    throw "Combined loss-report rebuild failed: $lossText"
}

$originalLogFiles = @(
    Get-ChildItem -LiteralPath $quickDir `
        -Filter "bench_v55_${tag}_part*.log" -File |
        Where-Object { $_.Name -notmatch '_err\.log$' } |
        Sort-Object Name
)
$allLogFiles = @($originalLogFiles.FullName) + @($repairLogFiles[0].FullName)
$logResult = & python -X utf8 `
    scripts/alpha_holdem/combine_slumbot_logs.py @allLogFiles 2>&1
$logExitCode = $LASTEXITCODE
$logText = $logResult -join "`n"
$logText | Out-File -FilePath (
    Join-Path $quickDir "bench_v55_${tag}_summary.txt"
) -Encoding utf8
if ($logExitCode -ne 0) {
    throw "Combined log summary rebuild failed: $logText"
}

$reportPath = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_standard10_bb_position_awr256_' +
        'fresh20k_20260727\report.json'
    )
).Path
$trainingReport = Get-Content -LiteralPath $reportPath -Raw |
    ConvertFrom-Json
$offlineDecisionSamples = (
    [int64]$trainingReport.train_rows + [int64]$trainingReport.val_rows
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
    throw 'Repaired position-AWR promotion workflow failed'
}

$quickDecision = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json
$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay10m_20260726\latest.pt'
    )
).Path
$sourceSummary = @(
    Get-ChildItem -LiteralPath (
        'models\bench_sourcev4_imitation_anchor_' +
        'mixedselfplay10m_pure_fresh20k_20260726'
    ) -Filter '*_ci_summary.json' -File
)
if ($sourceSummary.Count -ne 1) {
    throw 'Expected one Standard10 fresh20k source summary'
}
$sourceExternal = Get-Content -LiteralPath $sourceSummary[0].FullName -Raw |
    ConvertFrom-Json
$experiment = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A conservative outcome-weighted BB-only neural residual can improve ' +
        'the weak BB seat while leaving the source SB policy unchanged.'
    )
    material_change = (
        'A zero-initialized 256-hidden position residual optimized only for BB ' +
        'from the source policy fresh20k decision evidence.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    source_external_hands = 20000
    source_external_bb_per_100 = [double]$sourceExternal.bb_per_100
    new_training_hands = 0
    inherited_lineage_training_hands = 10283876
    offline_decision_samples = $offlineDecisionSamples
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    external_result = [ordered]@{
        evaluation = 'greedy-direct fresh5k'
        hands = [int]$quickDecision.quick5k_hands
        summary = $ciSummary
        bb_per_100 = [double]$quickDecision.quick5k_bb_per_100
        ci95_lower = [double]$quickDecision.quick5k_ci95_lower
        ci95_upper = [double]$quickDecision.quick5k_ci95_upper
        repair = (
            'One replacement hand appended after one original network failure; ' +
            'all 4,999 original raw hands and dumps preserved unchanged.'
        )
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
    Set-Content -LiteralPath (
        'models\sourcev4_standard10_bb_position_awr256_' +
        'fresh20k_20260727\experiment_record.json'
    ) -Encoding UTF8

Write-Host (
    "Repaired fresh5k: hands=$($quickDecision.quick5k_hands) " +
    "bb/100=$($quickDecision.quick5k_bb_per_100) " +
    "CI95=[$($quickDecision.quick5k_ci95_lower)," +
    "$($quickDecision.quick5k_ci95_upper)] " +
    "promote=$($quickDecision.promote_to_fresh20k)"
)
