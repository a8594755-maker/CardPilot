$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
        'selected.pt'
    )
).Path
$outputDir = 'models\sourcev4_heroawr_bbpreflop_awr100k_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "BB-preflop AWR output already exists: $outputDir"
}

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
    --street-max 0 `
    --max-rows 100000 `
    --min-rows 20000 `
    --seed 20260804 `
    --device cuda `
    --epochs 3 `
    --batch-size 2048 `
    --lr 0.00005 `
    --kl-coef 1.0 `
    --return-clip-bb 20 `
    --beta-bb 2.5 `
    --min-bucket-count 50 `
    --weight-min 0.05 `
    --weight-max 20 `
    --slice-balance-power 0.0 `
    --decision-risk-power 0.0 `
    --val-fraction 0.05 `
    --separate-preflop-head-only
if ($LASTEXITCODE -ne 0) {
    throw 'BB-preflop AWR training failed'
}

$curveDir = Join-Path $outputDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
$candidates = [ordered]@{
    source = $source
    epoch1 = (Join-Path $outputDir 'epoch_1.pt')
    epoch2 = (Join-Path $outputDir 'epoch_2.pt')
    epoch3 = (Join-Path $outputDir 'epoch_3.pt')
}
$rows = foreach ($entry in $candidates.GetEnumerator()) {
    $json = Join-Path $curveDir "$($entry.Key).json"
    $probeOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260777 `
        --policy-mode greedy `
        --out-json $json `
        --out-md (Join-Path $curveDir "$($entry.Key).md")
    $probeOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "BB-preflop AWR internal probe failed: $($entry.Key)"
    }
    $probe = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
    [pscustomobject]@{
        name = $entry.Key
        checkpoint = $entry.Value
        mean_bb_per_100 = [double](
            ($probe.results | Measure-Object -Property bb100 -Average).Average
        )
        total_hands = [int64]$probe.checkpoint.total_hands
        results = $probe.results
    }
}
$sourceRow = $rows | Where-Object name -eq 'source'
$best = $rows |
    Where-Object name -ne 'source' |
    Sort-Object mean_bb_per_100 -Descending |
    Select-Object -First 1
$retain = (
    [double]$best.mean_bb_per_100 -ge
    ([double]$sourceRow.mean_bb_per_100 - 20.0)
)
$report = Get-Content -LiteralPath (Join-Path $outputDir 'report.json') -Raw |
    ConvertFrom-Json
$offlineRows = [int64]$report.train_rows + [int64]$report.val_rows
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'Training the BB-only preflop head with return-weighted historical hero ' +
        'actions reduces weak BB calls while preserving general play.'
    )
    material_change = (
        'Only the dedicated preflop head is optimized on 100k historical ' +
        'big-blind preflop decisions; postflop actor tensors remain frozen.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = 0
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = $offlineRows
    curve = $rows
    selected_checkpoint = $best.checkpoint
    selected_mean_bb_per_100 = [double]$best.mean_bb_per_100
    source_mean_bb_per_100 = [double]$sourceRow.mean_bb_per_100
    external_gate = 'best trained epoch >= source stable-internal mean - 20'
    run_fresh5k = $retain
    decision = if ($retain) { 'RETAIN_AND_SCREEN' } else { 'REJECT' }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $outputDir 'experiment_record.json') `
        -Encoding UTF8
if (-not $retain) { exit 0 }

$selected = Join-Path $outputDir 'selected.pt'
Copy-Item -LiteralPath $best.checkpoint -Destination $selected
$externalDir = 'models\bench_sourcev4_heroawr_bbpreflop_awr100k_pure_fresh5k_20260726'
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_heroawr_bbpreflop_awr100k_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'BB-preflop AWR fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_bbpreflop_awr100k' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_heroawr_bbpreflop_awr100k' `
    -TrainingMethod 'BB-only preflop-head offline AWR from historical hero decisions' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples $offlineRows
exit $LASTEXITCODE
