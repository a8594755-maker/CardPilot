$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$baseStem = 'sourcev4_position_teacher_standardSB_bbweight3BB'
$baseQuickDir = Join-Path 'models' "bench_${baseStem}_pure_fresh5k_20260727"
$baseDecisionPath = Join-Path $baseQuickDir 'promotion_decision.json'
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $baseDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $baseDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $baseDecisionPath"
}
$baseDecision = Get-Content -LiteralPath $baseDecisionPath -Raw |
    ConvertFrom-Json
if ([bool]$baseDecision.promote_to_fresh20k) {
    $baseTwentyDir = Join-Path (
        'models'
    ) "bench_${baseStem}_pure_fresh20k_20260726"
    $baseFormalDecisionPath = Join-Path (
        $baseTwentyDir
    ) 'formal100k_decision.json'
    while (
        -not (
            Test-Path -LiteralPath $baseFormalDecisionPath -PathType Leaf
        ) -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 20
    }
    if (
        -not (
            Test-Path -LiteralPath $baseFormalDecisionPath -PathType Leaf
        )
    ) {
        throw "Timed out waiting for $baseFormalDecisionPath"
    }
    $baseFormalDecision = Get-Content -LiteralPath (
        $baseFormalDecisionPath
    ) -Raw | ConvertFrom-Json
    if ([bool]$baseFormalDecision.formal_eligible) {
        $formalPolicy = (
            Resolve-Path -LiteralPath $baseFormalDecision.frozen_policy
        ).Path
        $formalSha = (
            Get-FileHash -LiteralPath $formalPolicy -Algorithm SHA256
        ).Hash.ToLowerInvariant()
        if (
            $formalSha -ne
            [string]$baseFormalDecision.frozen_policy_sha256
        ) {
            throw 'Position64 formal-policy hash mismatch'
        }
        $formalDir = Join-Path (
            'models'
        ) "bench_${baseStem}_pure_formal100k_20260727"
        if (Test-Path -LiteralPath $formalDir) {
            throw "Position64 formal100k output already exists: $formalDir"
        }
        New-Item -ItemType Directory -Path $formalDir | Out-Null
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
            'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
            -ModelPath $formalPolicy `
            -Tag "${baseStem}_pure_formal100k_20260727" `
            -HandsPerSession 5000 `
            -Sessions 20 `
            -OutputDir (Resolve-Path -LiteralPath $formalDir).Path `
            -PolicyMode greedy `
            -Strategy model
        exit $LASTEXITCODE
    }
    Write-Output (
        'The 64-hidden position model failed its completed fresh20k ' +
        'formal gate; screening the stronger 2048-hidden fallback.'
    )
}

$awrStem = 'sourcev4_standard10_bb_position_awr256_fresh20k'
$awrQuickDir = Join-Path 'models' "bench_${awrStem}_pure_fresh5k_20260727"
$awrDecisionPath = Join-Path $awrQuickDir 'promotion_decision.json'
while (
    -not (Test-Path -LiteralPath $awrDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $awrDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $awrDecisionPath"
}
$awrDecision = Get-Content -LiteralPath $awrDecisionPath -Raw |
    ConvertFrom-Json
if ([bool]$awrDecision.promote_to_fresh20k) {
    $awrTwentyDir = Join-Path (
        'models'
    ) "bench_${awrStem}_pure_fresh20k_20260726"
    $awrFormalDecisionPath = Join-Path (
        $awrTwentyDir
    ) 'formal100k_decision.json'
    while (
        -not (
            Test-Path -LiteralPath $awrFormalDecisionPath -PathType Leaf
        ) -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 20
    }
    if (
        -not (
            Test-Path -LiteralPath $awrFormalDecisionPath -PathType Leaf
        )
    ) {
        throw "Timed out waiting for $awrFormalDecisionPath"
    }
    $awrFormalDecision = Get-Content -LiteralPath (
        $awrFormalDecisionPath
    ) -Raw | ConvertFrom-Json
    if ([bool]$awrFormalDecision.formal_eligible) {
        Write-Output (
            'The isolated BB position-AWR candidate reached its formal gate; ' +
            'the lower-priority h2048 teacher fallback is no longer needed.'
        )
        exit 0
    }
}

# The h2048 teacher is a lower-information capacity retry after h64 failed
# externally. Let the already-running 60M lineage queue finish first.
do {
    $mainQueue = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -match (
                    '\\screen_imitation_anchor_' +
                    'followups_20260726\.ps1'
                )
            }
    )
    if ($mainQueue.Count -eq 0) { break }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if ($mainQueue.Count -ne 0) {
    throw 'Timed out waiting for the 60M external-screen queue'
}
do {
    $scaledQueue = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -match (
                    '\\screen_scaled_imitation_' +
                    'after_followups_20260727\.ps1'
                )
            }
    )
    if ($scaledQueue.Count -eq 0) { break }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if ($scaledQueue.Count -ne 0) {
    throw 'Timed out waiting for the scaled-opponent external-screen queue'
}

$recordPath = (
    'models\sourcev4_position_teacher_' +
    'standardSB_bbweight3BB_h2048_20260727\experiment_record.json'
)
$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
if ([string]$record.decision -ne 'READY_FOR_PURE_FRESH5K') {
    throw "Position-teacher h2048 candidate is not ready: $($record.decision)"
}
if (
    -not [bool]$record.pure_weight_policy -or
    [bool]$record.evaluator_side_overrides
) {
    throw 'Position-teacher h2048 candidate violates the pure-weight contract'
}
$checkpoint = (Resolve-Path -LiteralPath $record.candidate_checkpoint).Path
$sha = (
    Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sha -ne [string]$record.candidate_checkpoint_sha256) {
    throw 'Position-teacher h2048 checkpoint hash mismatch'
}

$stem = "${baseStem}_h2048"
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    $existingQuickArtifacts = @(
        Get-ChildItem -LiteralPath $quickDir -Force
    )
    if ($existingQuickArtifacts.Count -ne 0) {
        throw "Position-teacher h2048 fresh5k output already exists: $quickDir"
    }
} else {
    New-Item -ItemType Directory -Path $quickDir | Out-Null
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint `
    -Tag "${stem}_pure_fresh5k_20260727" `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Position-teacher h2048 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_position_teacher_standardSB_bbweight3BB_h2048' `
    -QuickDir $quickDir `
    -SourcePolicy $checkpoint `
    -OutputStem $stem `
    -TrainingMethod 'pure-position-teacher-dual-expert-distillation-h2048' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands (
        [int64]$record.inherited_lineage_training_hands
    ) `
    -OfflineDecisionSamples ([int64]$record.offline_decision_samples) `
    -DeferFormal
if ($LASTEXITCODE -ne 0) {
    throw 'Position-teacher h2048 promotion workflow failed'
}

$fallbackDecisionPath = Join-Path $quickDir 'promotion_decision.json'
$fallbackDecision = Get-Content -LiteralPath $fallbackDecisionPath -Raw |
    ConvertFrom-Json
if (-not [bool]$fallbackDecision.promote_to_fresh20k) {
    exit 0
}

$fallbackTwentyDir = Join-Path (
    'models'
) "bench_${stem}_pure_fresh20k_20260726"
$fallbackFormalDecisionPath = Join-Path (
    $fallbackTwentyDir
) 'formal100k_decision.json'
$fallbackFormalDecision = Get-Content -LiteralPath (
    $fallbackFormalDecisionPath
) -Raw | ConvertFrom-Json
if (-not [bool]$fallbackFormalDecision.formal_eligible) {
    exit 0
}

$fallbackFormalPolicy = (
    Resolve-Path -LiteralPath $fallbackFormalDecision.frozen_policy
).Path
$fallbackFormalSha = (
    Get-FileHash -LiteralPath $fallbackFormalPolicy -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $fallbackFormalSha -ne
    [string]$fallbackFormalDecision.frozen_policy_sha256
) {
    throw 'Position2048 formal-policy hash mismatch'
}
$fallbackFormalDir = Join-Path (
    'models'
) "bench_${stem}_pure_formal100k_20260727"
if (Test-Path -LiteralPath $fallbackFormalDir) {
    throw "Position2048 formal100k output already exists: $fallbackFormalDir"
}
New-Item -ItemType Directory -Path $fallbackFormalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $fallbackFormalPolicy `
    -Tag "${stem}_pure_formal100k_20260727" `
    -HandsPerSession 5000 `
    -Sessions 20 `
    -OutputDir (Resolve-Path -LiteralPath $fallbackFormalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
