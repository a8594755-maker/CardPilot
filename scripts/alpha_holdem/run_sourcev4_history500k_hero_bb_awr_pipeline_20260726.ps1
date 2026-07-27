$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$outputDir = 'models\sourcev4_history500k_hero_bb_awr_adapter256_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "Historical hero-BB AWR output already exists: $outputDir"
}
$source = 'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt'
& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint $source `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor hero `
    --position 0 `
    --street-min 0 `
    --street-max 3 `
    --max-rows 500000 `
    --min-rows 100000 `
    --seed 20260768 `
    --device cuda `
    --epochs 3 `
    --batch-size 2048 `
    --lr 0.0001 `
    --kl-coef 1.0 `
    --return-clip-bb 20 `
    --beta-bb 5 `
    --min-bucket-count 50 `
    --weight-min 0.05 `
    --weight-max 20 `
    --slice-balance-power 0.0 `
    --decision-risk-power 0.0 `
    --val-fraction 0.05 `
    --postflop-adapter-hidden 256 `
    --policy-adapter-only
if ($LASTEXITCODE -ne 0) {
    throw 'Historical hero-BB AWR training failed'
}

$curveDir = Join-Path $outputDir 'short_common_seed_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
$candidates = [ordered]@{
    full_hero_epoch1 = 'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\epoch_1.pt'
    hero_bb_epoch1 = Join-Path $outputDir 'epoch_1.pt'
    hero_bb_epoch2 = Join-Path $outputDir 'epoch_2.pt'
    hero_bb_epoch3 = Join-Path $outputDir 'epoch_3.pt'
}
foreach ($name in $candidates.Keys) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidates[$name] `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260769 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "$name.json") `
        --out-md (Join-Path $curveDir "$name.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Historical hero-BB short probe failed for $name"
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
    $ranked | Where-Object { $_.name -eq 'full_hero_epoch1' }
)[0]
$bestFocused = @(
    $ranked | Where-Object { $_.name -match '^hero_bb_epoch' }
)[0]
$launch = (
    [double]$bestFocused.mean_bb_per_100 -ge
    ([double]$baseline.mean_bb_per_100 + 10.0)
)
$selection = [ordered]@{
    schema = 'cardpilot.discovery_selection.v1'
    hypothesis = 'Historical successful hero BB decisions can directly improve the localized big-blind loss while leaving SB behavior source-anchored.'
    proxy_only = $true
    common_seed = 20260769
    hands_per_scripted_opponent = 1000
    ranked = $ranked
    selection_rule = 'best hero-BB epoch mean >= full hero-AWR epoch1 mean + 10 bb/100'
    launch_fresh5k = $launch
    selected = $bestFocused
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
$selection | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $curveDir 'selection.json') -Encoding UTF8
if (-not $launch) { exit 0 }

$selected = Join-Path $outputDir 'selected.pt'
Copy-Item -LiteralPath $bestFocused.checkpoint -Destination $selected
$externalDir = 'models\bench_sourcev4_history500k_hero_bb_awr_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_history500k_hero_bb_awr_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Historical hero-BB AWR fresh5k failed'
}

$report = Get-Content -LiteralPath (Join-Path $outputDir 'report.json') -Raw |
    ConvertFrom-Json
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_history500k_hero_bb_awr_selected' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_history500k_hero_bb_awr_selected' `
    -TrainingMethod 'BB-only advantage-weighted regression on historical hero Slumbot decisions' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples ([int64]$report.ingest.position_filtered_rows)
exit $LASTEXITCODE
