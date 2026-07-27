$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$recordPath = (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727\experiment_record.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $recordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $recordPath -PathType Leaf)) {
    throw "Timed out waiting for $recordPath"
}

# Keep one external-evaluation slot. The main follow-up queue owns it first.
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
    throw 'Timed out waiting for the main external-evaluation queue'
}

function Invoke-RecordScreen {
    param(
        [Parameter(Mandatory = $true)][pscustomobject]$Record,
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Stem,
        [Parameter(Mandatory = $true)][string]$TrainingMethod,
        [Parameter(Mandatory = $true)][string]$HashFailureLabel
    )
    if ([string]$Record.decision -ne 'READY_FOR_PURE_FRESH5K') {
        Write-Output "$Candidate failed its held-out gate; screen skipped."
        return
    }
    $checkpoint = (
        Resolve-Path -LiteralPath $Record.candidate_checkpoint
    ).Path
    $sha = (
        Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($sha -ne [string]$Record.candidate_checkpoint_sha256) {
        throw "$HashFailureLabel checkpoint hash mismatch"
    }

    $quickDir = Join-Path 'models' "bench_${Stem}_pure_fresh5k_20260727"
    if (Test-Path -LiteralPath $quickDir) {
        $existingSummary = @(
            Get-ChildItem -LiteralPath $quickDir `
                -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
        )
        if (
            $existingSummary.Count -eq 1 -and
            (Test-Path -LiteralPath (
                Join-Path $quickDir 'promotion_decision.json'
            ) -PathType Leaf)
        ) {
            Write-Output "$Candidate already has a completed fresh5k; skipped."
            return
        }
        throw "$Candidate incomplete fresh5k output already exists: $quickDir"
    }
    New-Item -ItemType Directory -Path $quickDir | Out-Null
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
        -ModelPath $checkpoint `
        -Tag "${Stem}_pure_fresh5k_20260727" `
        -HandsPerSession 500 `
        -Sessions 10 `
        -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
        -PolicyMode greedy `
        -Strategy model
    if ($LASTEXITCODE -ne 0) {
        throw "$Candidate fresh5k failed"
    }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
        -Candidate $Candidate `
        -QuickDir $quickDir `
        -SourcePolicy $checkpoint `
        -OutputStem $Stem `
        -TrainingMethod $TrainingMethod `
        -NewTrainingHands ([int64]$Record.new_training_hands) `
        -InheritedLineageTrainingHands (
            [int64]$Record.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples (
            if ($null -ne $Record.offline_decision_samples) {
                [int64]$Record.offline_decision_samples
            } else {
                [int64]$Record.inherited_offline_decision_samples
            }
        )
    if ($LASTEXITCODE -ne 0) {
        throw "$Candidate promotion pipeline failed"
    }
}

function Invoke-BestResponseScreen {
    param([Parameter(Mandatory = $true)][string]$RecordPath)
    $bestResponseRecord = Get-Content -LiteralPath $RecordPath -Raw |
        ConvertFrom-Json
    Invoke-RecordScreen `
        -Record $bestResponseRecord `
        -Candidate 'sourcev4_standard10_scaledopponent_bestresponse20m' `
        -Stem 'sourcev4_standard10_scaledopponent_bestresponse20m' `
        -TrainingMethod (
            'standard10 strong-KL PPO versus scaled Slumbot-opponent league'
        ) `
        -HashFailureLabel 'Scaled-opponent best response'
}

$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$bestResponseRecordPath = (
    'models\sourcev4_standard10_scaledopponent_' +
    'bestresponse20m_20260727\experiment_record.json'
)
$bestResponseScreened = $false
if (
    [string]$record.decision -eq 'READY_FOR_PURE_FRESH5K' -and
    (Test-Path -LiteralPath $bestResponseRecordPath -PathType Leaf)
) {
    Invoke-BestResponseScreen -RecordPath $bestResponseRecordPath
    $bestResponseScreened = $true
}

Invoke-RecordScreen `
    -Record $record `
    -Candidate 'sourcev4_slumbot_allstreet_imitation_scale1p25m' `
    -Stem 'sourcev4_slumbot_allstreet_imitation_scale1p25m' `
    -TrainingMethod 'all-street-Slumbot-imitation-scale1p25m' `
    -HashFailureLabel 'Scaled imitation'

if (
    [string]$record.decision -eq 'READY_FOR_PURE_FRESH5K' -and
    -not $bestResponseScreened
) {
    while (
        -not (
            Test-Path -LiteralPath $bestResponseRecordPath -PathType Leaf
        ) -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 20
    }
    if (
        -not (
            Test-Path -LiteralPath $bestResponseRecordPath -PathType Leaf
        )
    ) {
        throw "Timed out waiting for $bestResponseRecordPath"
    }
    Invoke-BestResponseScreen -RecordPath $bestResponseRecordPath
}

$positionRecordPath = (
    'models\sourcev4_position_teacher_' +
    'standardSB_bbweight3BB_20260727\experiment_record.json'
)
while (
    -not (Test-Path -LiteralPath $positionRecordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $positionRecordPath -PathType Leaf)) {
    throw "Timed out waiting for $positionRecordPath"
}
$positionRecord = Get-Content -LiteralPath $positionRecordPath -Raw |
    ConvertFrom-Json
Invoke-RecordScreen `
    -Record $positionRecord `
    -Candidate 'sourcev4_position_teacher_standardSB_bbweight3BB' `
    -Stem 'sourcev4_position_teacher_standardSB_bbweight3BB' `
    -TrainingMethod 'pure-position-teacher-dual-expert-distillation' `
    -HashFailureLabel 'Position distillation'
exit 0
