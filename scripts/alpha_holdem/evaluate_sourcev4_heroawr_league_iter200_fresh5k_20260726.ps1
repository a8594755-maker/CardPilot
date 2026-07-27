$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$precedingQuickDir = (
    Resolve-Path -LiteralPath (
        'models\bench_sourcev4_postflop_adapter128_rl_conservative2m_' +
        'selected_pure_fresh5k_20260726'
    )
).Path
$deadline = (Get-Date).AddHours(4)
while ((Get-Date) -lt $deadline) {
    $summary = @(
        Get-ChildItem -LiteralPath $precedingQuickDir `
            -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
    )
    if ($summary.Count -eq 1) { break }
    Start-Sleep -Seconds 30
}
$summary = @(
    Get-ChildItem -LiteralPath $precedingQuickDir `
        -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
)
if ($summary.Count -ne 1) {
    throw 'Conservative-2M fresh5k did not finish before the deadline'
}

$checkpoint = @(
    Get-ChildItem -Path (
        'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
        'checkpoints\checkpoint_iter000200_*.pt'
    ) -File
)
if ($checkpoint.Count -ne 1) {
    throw "Expected one iteration-200 checkpoint, found $($checkpoint.Count)"
}

$outputDir = (
    'models\bench_sourcev4_heroawr_mimic_league_iter200_' +
    'pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "External output already exists: $outputDir"
}
New-Item -ItemType Directory -Path $outputDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint[0].FullName `
    -Tag 'sourcev4_heroawr_mimic_league_iter200_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $outputDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Hero-AWR mimic-league iteration-200 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_mimic_league_iter200' `
    -QuickDir $outputDir `
    -SourcePolicy $checkpoint[0].FullName `
    -OutputStem 'sourcev4_heroawr_mimic_league_iter200' `
    -TrainingMethod (
        'five-member fixed pure-policy opponent-league PPO from hero-AWR weights; ' +
        'iteration-200 stable-internal-curve selection'
    ) `
    -NewTrainingHands 6308783 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
