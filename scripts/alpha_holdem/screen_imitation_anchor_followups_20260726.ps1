param(
    [switch]$SkipSpecialist
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

function Wait-ForPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][datetime]$Deadline
    )
    while (
        -not (Test-Path -LiteralPath $Path -PathType Leaf) -and
        (Get-Date) -lt $Deadline
    ) {
        Start-Sleep -Seconds 20
    }
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Timed out waiting for $Path"
    }
}

function Wait-ForStandardPipeline {
    param([Parameter(Mandatory = $true)][datetime]$Deadline)
    do {
        $running = @(
            Get-CimInstance Win32_Process |
                Where-Object {
                    $_.CommandLine -match (
                        '\\run_sourcev4_imitation_anchor_' +
                        'mixedselfplay10m_20260726\.ps1'
                    )
                }
        )
        if ($running.Count -eq 0) { return }
        Start-Sleep -Seconds 20
    } while ((Get-Date) -lt $Deadline)
    throw 'Timed out waiting for the standard imitation-anchor pipeline'
}

function Invoke-CandidateScreen {
    param(
        [Parameter(Mandatory = $true)][string]$Candidate,
        [Parameter(Mandatory = $true)][string]$Checkpoint,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$OutputStem,
        [Parameter(Mandatory = $true)][string]$TrainingMethod,
        [Parameter(Mandatory = $true)][long]$NewTrainingHands,
        [Parameter(Mandatory = $true)][long]$InheritedLineageTrainingHands,
        [Parameter(Mandatory = $true)][long]$OfflineDecisionSamples,
        [double]$QuickPromoteBB100 = 0.0
    )
    $checkpointPath = (Resolve-Path -LiteralPath $Checkpoint).Path
    $observedSha = (
        Get-FileHash -LiteralPath $checkpointPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($observedSha -ne $ExpectedSha256) {
        throw "$Candidate checkpoint hash mismatch"
    }

    $quickDir = Join-Path 'models' "bench_${OutputStem}_pure_fresh5k_20260726"
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
    @{
        schema = 'cardpilot.external_evaluation_isolation.v1'
        candidate_checkpoint_sha256 = $observedSha
        evaluation_started_after_checkpoint_freeze = (
            Get-Date
        ).ToUniversalTime().ToString('o')
        evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
        preexisting_slumbot_hands_reused = $false
    } | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (
            Join-Path $quickDir 'evaluation_isolation.json'
        ) -Encoding UTF8
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
        -ModelPath $checkpointPath `
        -Tag "${OutputStem}_pure_fresh5k_20260726" `
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
        -SourcePolicy $checkpointPath `
        -OutputStem $OutputStem `
        -TrainingMethod $TrainingMethod `
        -NewTrainingHands $NewTrainingHands `
        -InheritedLineageTrainingHands $InheritedLineageTrainingHands `
        -OfflineDecisionSamples $OfflineDecisionSamples `
        -QuickPromoteBB100 $QuickPromoteBB100
    if ($LASTEXITCODE -ne 0) {
        throw "$Candidate promotion pipeline failed"
    }
}

$deadline = [datetime]'2026-08-01T23:30:00'

# The standard pipeline owns the first external slot and may promote itself.
Wait-ForStandardPipeline -Deadline $deadline

if (-not $SkipSpecialist) {
    $specialistRecordPath = (
        'models\sourcev4_imitation_anchor_' +
        'specialist10m_from10m_20260726\experiment_record.json'
    )
    Wait-ForPath -Path $specialistRecordPath -Deadline $deadline
    $specialistRecord = Get-Content -LiteralPath $specialistRecordPath -Raw |
        ConvertFrom-Json
    Invoke-CandidateScreen `
        -Candidate 'sourcev4_imitation_anchor_specialist10m_from10m' `
        -Checkpoint ([string]$specialistRecord.candidate_checkpoint) `
        -ExpectedSha256 ([string]$specialistRecord.candidate_checkpoint_sha256) `
        -OutputStem 'sourcev4_imitation_anchor_specialist10m_from10m' `
        -TrainingMethod 'imitation-anchor-Slumbot-specialist-PPO' `
        -NewTrainingHands ([int64]$specialistRecord.new_training_hands) `
        -InheritedLineageTrainingHands (
            [int64]$specialistRecord.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples (
            [int64]$specialistRecord.inherited_offline_decision_samples
        )
}

$fiftyRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay50m_from10m_20260726\experiment_record.json'
)
$fiftyScreened = $false
if (Test-Path -LiteralPath $fiftyRecordPath -PathType Leaf) {
    $fiftyRecord = Get-Content -LiteralPath $fiftyRecordPath -Raw |
        ConvertFrom-Json
    Invoke-CandidateScreen `
        -Candidate 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -Checkpoint ([string]$fiftyRecord.candidate_checkpoint) `
        -ExpectedSha256 ([string]$fiftyRecord.candidate_checkpoint_sha256) `
        -OutputStem 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -TrainingMethod (
            'imitation-anchor-strong-KL-mixed-self-play-PPO-50M-extension'
        ) `
        -NewTrainingHands ([int64]$fiftyRecord.new_training_hands) `
        -InheritedLineageTrainingHands (
            [int64]$fiftyRecord.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples (
            [int64]$fiftyRecord.inherited_offline_decision_samples
        ) `
        -QuickPromoteBB100 -10
    $fiftyScreened = $true
}

$evRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay_allinev10m_20260726\experiment_record.json'
)
Wait-ForPath -Path $evRecordPath -Deadline $deadline
$evRecord = Get-Content -LiteralPath $evRecordPath -Raw | ConvertFrom-Json
Invoke-CandidateScreen `
    -Candidate 'sourcev4_imitation_anchor_mixedselfplay_allinev10m' `
    -Checkpoint ([string]$evRecord.candidate_checkpoint) `
    -ExpectedSha256 ([string]$evRecord.candidate_checkpoint_sha256) `
    -OutputStem 'sourcev4_imitation_anchor_mixedselfplay_allinev10m' `
    -TrainingMethod 'imitation-anchor-strong-KL-mixed-self-play-PPO-allin-EV' `
    -NewTrainingHands ([int64]$evRecord.new_training_hands) `
    -InheritedLineageTrainingHands (
        [int64]$evRecord.inherited_lineage_training_hands
    ) `
    -OfflineDecisionSamples (
        [int64]$evRecord.inherited_offline_decision_samples
    )

$fiftyReadyAfterEv = (
    Test-Path -LiteralPath $fiftyRecordPath -PathType Leaf
)
if (-not $fiftyScreened -and $fiftyReadyAfterEv) {
    $fiftyRecord = Get-Content -LiteralPath $fiftyRecordPath -Raw |
        ConvertFrom-Json
    Invoke-CandidateScreen `
        -Candidate 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -Checkpoint ([string]$fiftyRecord.candidate_checkpoint) `
        -ExpectedSha256 ([string]$fiftyRecord.candidate_checkpoint_sha256) `
        -OutputStem 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -TrainingMethod (
            'imitation-anchor-strong-KL-mixed-self-play-PPO-50M-extension'
        ) `
        -NewTrainingHands ([int64]$fiftyRecord.new_training_hands) `
        -InheritedLineageTrainingHands (
            [int64]$fiftyRecord.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples (
            [int64]$fiftyRecord.inherited_offline_decision_samples
        ) `
        -QuickPromoteBB100 -10
    $fiftyScreened = $true
}

$bbRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726\experiment_record.json'
)
Wait-ForPath -Path $bbRecordPath -Deadline $deadline
$bbRecord = Get-Content -LiteralPath $bbRecordPath -Raw | ConvertFrom-Json
$bbDirectionalGain = (
    [double]$bbRecord.selected_overall_accuracy -ge
        [double]$bbRecord.source_overall_accuracy -and
    [double]$bbRecord.selected_p0_preflop_accuracy -ge
        ([double]$bbRecord.source_p0_preflop_accuracy + 0.02) -and
    [double]$bbRecord.selected_p1_preflop_accuracy -ge 0.70
)
if (
    [string]$bbRecord.decision -eq 'READY_FOR_PURE_FRESH5K' -or
    $bbDirectionalGain
) {
    Invoke-CandidateScreen `
        -Candidate 'sourcev4_slumbot_allstreet_imitation_bbweight3' `
        -Checkpoint ([string]$bbRecord.selected_checkpoint) `
        -ExpectedSha256 ([string]$bbRecord.selected_checkpoint_sha256) `
        -OutputStem 'sourcev4_slumbot_allstreet_imitation_bbweight3' `
        -TrainingMethod 'all-street-Slumbot-imitation-BB-weight3' `
        -NewTrainingHands 0 `
        -InheritedLineageTrainingHands (
            [int64]$bbRecord.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples ([int64]$bbRecord.offline_decision_samples)
}

if (-not $fiftyScreened) {
    # Finish the already-running Standard32 fresh20k (including any exact-hand
    # supplement) before putting Standard60 into the serialized Slumbot queue.
    # This lets a plausible frozen Standard32 policy claim the formal slot
    # immediately, while a rejected endpoint adds only a few seconds of delay.
    $standard32DecisionPath = (
        'models\bench_sourcev4_imitation_anchor_' +
        'mixedselfplay32m_pure_fresh20k_20260726\' +
        'formal100k_decision.json'
    )
    Wait-ForPath -Path $standard32DecisionPath -Deadline $deadline
    Wait-ForPath -Path $fiftyRecordPath -Deadline $deadline
    $fiftyRecord = Get-Content -LiteralPath $fiftyRecordPath -Raw |
        ConvertFrom-Json
    Invoke-CandidateScreen `
        -Candidate 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -Checkpoint ([string]$fiftyRecord.candidate_checkpoint) `
        -ExpectedSha256 ([string]$fiftyRecord.candidate_checkpoint_sha256) `
        -OutputStem 'sourcev4_imitation_anchor_mixedselfplay50m_from10m' `
        -TrainingMethod (
            'imitation-anchor-strong-KL-mixed-self-play-PPO-50M-extension'
        ) `
        -NewTrainingHands ([int64]$fiftyRecord.new_training_hands) `
        -InheritedLineageTrainingHands (
            [int64]$fiftyRecord.inherited_lineage_training_hands
        ) `
        -OfflineDecisionSamples (
            [int64]$fiftyRecord.inherited_offline_decision_samples
        ) `
        -QuickPromoteBB100 -10
}

$specialistMixedRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'specialist_mixed40m_from20m_20260726\experiment_record.json'
)
Wait-ForPath -Path $specialistMixedRecordPath -Deadline $deadline
$specialistMixedRecord = Get-Content -LiteralPath $specialistMixedRecordPath `
    -Raw | ConvertFrom-Json
Invoke-CandidateScreen `
    -Candidate 'sourcev4_imitation_anchor_specialist_mixed40m_from20m' `
    -Checkpoint ([string]$specialistMixedRecord.candidate_checkpoint) `
    -ExpectedSha256 (
        [string]$specialistMixedRecord.candidate_checkpoint_sha256
    ) `
    -OutputStem 'sourcev4_imitation_anchor_specialist_mixed40m_from20m' `
    -TrainingMethod (
        'Slumbot-specialist-then-25pct-self-play-PPO-40M-extension'
    ) `
    -NewTrainingHands ([int64]$specialistMixedRecord.new_training_hands) `
    -InheritedLineageTrainingHands (
        [int64]$specialistMixedRecord.inherited_lineage_training_hands
    ) `
    -OfflineDecisionSamples (
        [int64]$specialistMixedRecord.inherited_offline_decision_samples
    )
exit 0
