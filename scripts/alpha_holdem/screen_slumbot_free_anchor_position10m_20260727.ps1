$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$recordPath = (
    'models\slumbot_free_anchor_position10m_20260727\' +
    'experiment_record.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
do {
    if (Test-Path -LiteralPath $recordPath -PathType Leaf) {
        $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
        if ([string]$record.status -eq 'READY_FOR_PURE_FRESH5K') {
            break
        }
        if ([string]$record.status -eq 'FAILED') {
            throw 'SLUMBOT_FREE training failed; external screen skipped'
        }
    }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if (
    -not (Test-Path -LiteralPath $recordPath -PathType Leaf) -or
    [string]$record.status -ne 'READY_FOR_PURE_FRESH5K'
) {
    throw 'Timed out waiting for the SLUMBOT_FREE endpoint'
}

# Preserve one external slot. Both existing queues must finish first.
do {
    $otherQueues = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -match (
                    '\\(screen_imitation_anchor_followups_20260726|' +
                    'screen_scaled_imitation_after_followups_20260727)\.ps1'
                )
            }
    )
    if ($otherQueues.Count -eq 0) { break }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if ($otherQueues.Count -ne 0) {
    throw 'Timed out waiting for the existing external-evaluation queues'
}

$checkpoint = (Resolve-Path -LiteralPath $record.candidate_checkpoint).Path
$sha = (
    Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sha -ne [string]$record.candidate_checkpoint_sha256) {
    throw 'SLUMBOT_FREE candidate hash mismatch'
}
$quickDir = (
    'models\bench_slumbot_free_anchor_position10m_' +
    'pure_fresh5k_20260727'
)
if (Test-Path -LiteralPath $quickDir) {
    throw "SLUMBOT_FREE external output already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint `
    -Tag 'slumbot_free_anchor_position10m_pure_fresh5k_20260727' `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'SLUMBOT_FREE fresh5k failed'
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'slumbot_free_anchor_position10m' `
    -QuickDir $quickDir `
    -SourcePolicy $checkpoint `
    -OutputStem 'slumbot_free_anchor_position10m' `
    -TrainingMethod 'clean-heuristic-anchor-position-aware-selfplay10m' `
    -NewTrainingHands ([int64]$record.new_training_hands) `
    -InheritedLineageTrainingHands 0 `
    -OfflineDecisionSamples 474983
if ($LASTEXITCODE -ne 0) {
    throw 'SLUMBOT_FREE promotion pipeline failed'
}
exit 0
