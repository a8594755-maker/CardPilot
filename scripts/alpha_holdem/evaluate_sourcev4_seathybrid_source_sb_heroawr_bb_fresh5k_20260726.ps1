$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sbModel = (
    Resolve-Path -LiteralPath (
        'models\slumbot_br_preflopv2_pokerskill_' +
        'direct_distill_v2_20260725\latest.pt'
    )
).Path
$bbModel = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_' +
        'adapter256_mappingfix_20260726\selected.pt'
    )
).Path
$outputDir = (
    'models\bench_sourcev4_seathybrid_source_sb_' +
    'heroawr_bb_pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $outputDir) {
    throw "Seat-hybrid external output already exists: $outputDir"
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -Tag 'sourcev4_seathybrid_source_sb_heroawr_bb_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $outputDir).Path `
    -PolicyMode greedy `
    -Strategy seat_hybrid `
    -SbModel $sbModel `
    -BbModel $bbModel
exit $LASTEXITCODE
