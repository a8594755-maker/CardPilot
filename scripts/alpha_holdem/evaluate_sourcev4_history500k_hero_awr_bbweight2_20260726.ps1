$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$outputDir = 'models\sourcev4_history500k_hero_awr_bbweight2_adapter256_20260726'
$reportPath = Join-Path $outputDir 'report.json'
$deadline = (Get-Date).AddHours(6)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $reportPath) { break }
    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'offline_slumbot_awr\.py' -and
                $_.CommandLine -match
                    'sourcev4_history500k_hero_awr_bbweight2_adapter256_20260726'
            }
    )
    if ($trainer.Count -eq 0) {
        throw 'BB-weighted hero-AWR trainer exited before report.json'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $reportPath)) {
    throw 'Timed out waiting for BB-weighted hero-AWR report.json'
}

$curveDir = Join-Path $outputDir 'short_common_seed_curve'
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
$candidates = [ordered]@{
    full_hero_epoch1 = 'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\epoch_1.pt'
    bbweight2_epoch1 = Join-Path $outputDir 'epoch_1.pt'
    bbweight2_epoch2 = Join-Path $outputDir 'epoch_2.pt'
    bbweight2_epoch3 = Join-Path $outputDir 'epoch_3.pt'
}
foreach ($name in $candidates.Keys) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidates[$name] `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260773 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "$name.json") `
        --out-md (Join-Path $curveDir "$name.md")
    if ($LASTEXITCODE -ne 0) {
        throw "BB-weighted hero-AWR common-seed probe failed for $name"
    }
}

$ranked = @(
    foreach ($name in $candidates.Keys) {
        $probe = Get-Content -LiteralPath (Join-Path $curveDir "$name.json") `
            -Raw | ConvertFrom-Json
        [PSCustomObject]@{
            name = $name
            checkpoint = (Resolve-Path -LiteralPath $candidates[$name]).Path
            mean_bb_per_100 = [double](
                ($probe.results | Measure-Object -Property bb100 -Average).Average
            )
        }
    }
) | Sort-Object mean_bb_per_100 -Descending
$baseline = @($ranked | Where-Object { $_.name -eq 'full_hero_epoch1' })[0]
$bestWeighted = @(
    $ranked | Where-Object { $_.name -match '^bbweight2_epoch' }
)[0]
$launch = (
    [double]$bestWeighted.mean_bb_per_100 -ge
    ([double]$baseline.mean_bb_per_100 + 10.0)
)
$selection = [ordered]@{
    schema = 'cardpilot.discovery_selection.v1'
    hypothesis = 'Doubling BB-row AWR weight while retaining both positions corrects the source policy BB weakness without sacrificing SB behavior.'
    proxy_only = $true
    common_seed = 20260773
    hands_per_scripted_opponent = 1000
    ranked = $ranked
    selection_rule = 'best BB-weighted epoch mean >= full-position epoch1 + 10 bb/100'
    launch_fresh5k = $launch
    selected = $bestWeighted
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
$selection | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $curveDir 'selection.json') -Encoding UTF8
if (-not $launch) { exit 0 }

$selected = Join-Path $outputDir 'selected.pt'
Copy-Item -LiteralPath $bestWeighted.checkpoint -Destination $selected
$externalDir =
    'models\bench_sourcev4_history500k_hero_awr_bbweight2_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_history500k_hero_awr_bbweight2_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'BB-weighted hero-AWR fresh5k failed'
}

$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
$offlineSamples = if ($null -ne $report.ingest.sampled_rows) {
    [int64]$report.ingest.sampled_rows
} else {
    [int64]$report.train_rows + [int64]$report.val_rows
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_history500k_hero_awr_bbweight2_selected' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_history500k_hero_awr_bbweight2_selected' `
    -TrainingMethod 'all-position historical-hero AWR with 2x BB row weight' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples $offlineSamples
exit $LASTEXITCODE
