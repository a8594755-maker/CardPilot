$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$checkpointDir = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay10m_20260726\checkpoints'
)
$deadline = (Get-Date).AddHours(1)
do {
    $candidates = @(
        Get-ChildItem -LiteralPath $checkpointDir `
            -Filter 'checkpoint_iter000100_hands*.pt' `
            -File -ErrorAction SilentlyContinue
    )
    if ($candidates.Count -eq 1) { break }
    if ($candidates.Count -gt 1) {
        throw 'More than one iteration-100 checkpoint exists'
    }
    Start-Sleep -Seconds 15
} while ((Get-Date) -lt $deadline)
if ($candidates.Count -ne 1) {
    throw 'Timed out waiting for the iteration-100 checkpoint'
}

$checkpoint = $candidates[0].FullName
if ($candidates[0].BaseName -notmatch '_hands0*(\d+)$') {
    throw "Could not parse checkpoint hand count: $($candidates[0].Name)"
}
$totalHands = [int64]$Matches[1]
$sourceHands = 262472
$newHands = $totalHands - $sourceHands
if ($newHands -lt 2500000 -or $newHands -gt 4000000) {
    throw "Unexpected iteration-100 new-hand count: $newHands"
}

$externalDir = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay_iter100_pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $externalDir) {
    throw "Iteration-100 screen output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint `
    -Tag 'sourcev4_imitation_anchor_mixedselfplay_iter100_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Iteration-100 imitation-anchor fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_imitation_anchor_mixedselfplay_iter100' `
    -QuickDir $externalDir `
    -SourcePolicy $checkpoint `
    -OutputStem 'sourcev4_imitation_anchor_mixedselfplay_iter100' `
    -TrainingMethod 'direct-imitation-anchor-strong-KL-mixed-self-play-PPO' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $sourceHands `
    -OfflineDecisionSamples 750000
exit $LASTEXITCODE
