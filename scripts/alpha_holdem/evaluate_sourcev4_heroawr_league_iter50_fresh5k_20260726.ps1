$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceQuickDir = (
    Resolve-Path -LiteralPath (
        'models\bench_sourcev4_history500k_hero_awr_selected_' +
        'pure_fresh5k_20260726'
    )
).Path
$deadline = (Get-Date).AddHours(4)
while ((Get-Date) -lt $deadline) {
    $summary = @(
        Get-ChildItem -LiteralPath $sourceQuickDir `
            -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
    )
    if ($summary.Count -eq 1) { break }
    Start-Sleep -Seconds 30
}
$summary = @(
    Get-ChildItem -LiteralPath $sourceQuickDir `
        -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
)
if ($summary.Count -ne 1) {
    throw 'Source hero-AWR fresh5k did not finish before the deadline'
}

$checkpoint = @(
    Get-ChildItem -Path (
        'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
        'checkpoints\checkpoint_iter000050_*.pt'
    ) -File
)
if ($checkpoint.Count -ne 1) {
    throw "Expected one iteration-50 checkpoint, found $($checkpoint.Count)"
}

$outputDir = (
    'models\bench_sourcev4_heroawr_mimic_league_iter50_' +
    'pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "External output already exists: $outputDir"
}
New-Item -ItemType Directory -Path $outputDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint[0].FullName `
    -Tag 'sourcev4_heroawr_mimic_league_iter50_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $outputDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Hero-AWR mimic-league iteration-50 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_mimic_league_iter50' `
    -QuickDir $outputDir `
    -SourcePolicy $checkpoint[0].FullName `
    -OutputStem 'sourcev4_heroawr_mimic_league_iter50' `
    -TrainingMethod (
        'five-member fixed pure-policy opponent-league PPO from hero-AWR weights; ' +
        'iteration-50 internal-curve selection'
    ) `
    -NewTrainingHands 1379221 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
