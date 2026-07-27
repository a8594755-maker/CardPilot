$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidateDir = 'models\sourcev4_slumbot_formal100k_bb_postflop_awr_adapter256_20260726'
$allPosition = 'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt'
$curveDir = Join-Path $candidateDir 'short_common_seed_curve'
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null

$candidates = [ordered]@{
    allpos_epoch1 = $allPosition
    bb_epoch1 = Join-Path $candidateDir 'epoch_1.pt'
    bb_epoch2 = Join-Path $candidateDir 'epoch_2.pt'
    bb_epoch3 = Join-Path $candidateDir 'epoch_3.pt'
}
foreach ($name in $candidates.Keys) {
    $result = Join-Path $curveDir "$name.json"
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidates[$name] `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260764 `
        --policy-mode greedy `
        --out-json $result `
        --out-md (Join-Path $curveDir "$name.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Short common-seed probe failed for $name"
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
$baseline = @(
    $ranked | Where-Object { $_.name -eq 'allpos_epoch1' }
)[0]
$bestBb = @(
    $ranked | Where-Object { $_.name -match '^bb_epoch' }
)[0]
$launch = (
    [double]$bestBb.mean_bb_per_100 -ge
    ([double]$baseline.mean_bb_per_100 + 10.0)
)
$selection = [ordered]@{
    schema = 'cardpilot.discovery_selection.v1'
    hypothesis = 'Formal100k Slumbot BB-only postflop AWR improves the localized big-blind defense weakness.'
    proxy_only = $true
    common_seed = 20260764
    hands_per_scripted_opponent = 1000
    ranked = $ranked
    selection_rule = 'best BB-only epoch mean >= all-position epoch1 mean + 10 bb/100'
    launch_fresh5k = $launch
    selected = $bestBb
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
$selection |
    ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $curveDir 'selection.json') -Encoding UTF8
if (-not $launch) {
    exit 0
}

$selected = Join-Path $candidateDir 'selected.pt'
Copy-Item -LiteralPath $bestBb.checkpoint -Destination $selected
$externalDir = 'models\bench_sourcev4_formal100k_bb_postflop_awr_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_formal100k_bb_postflop_awr_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
