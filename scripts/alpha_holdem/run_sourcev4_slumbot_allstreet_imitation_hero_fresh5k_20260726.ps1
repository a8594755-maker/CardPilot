$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidateDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726'
)
$record = Get-Content -LiteralPath (
    Join-Path $candidateDir 'experiment_record.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath $record.candidate_checkpoint).Path
$observedSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($observedSha -ne [string]$record.candidate_checkpoint_sha256) {
    throw 'All-street imitation candidate hash mismatch'
}
if (
    [double]$record.candidate_validation_accuracy -lt 0.70 -or
    [double]$record.candidate_preflop_min_validation_accuracy -lt 0.50
) {
    throw 'All-street imitation candidate no longer satisfies held-out gate'
}

$externalDir = (
    'models\bench_sourcev4_slumbot_allstreet_imitation_' +
    'fullnet_hero_pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $externalDir) {
    throw "Hero imitation fresh5k output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag `
    'sourcev4_slumbot_allstreet_imitation_fullnet_hero_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'All-street imitation hero fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_slumbot_allstreet_imitation_fullnet_hero' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_slumbot_allstreet_imitation_fullnet_hero' `
    -TrainingMethod 'all-street-offline-Slumbot-behavior-cloning' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 262472 `
    -OfflineDecisionSamples 750000
exit $LASTEXITCODE
