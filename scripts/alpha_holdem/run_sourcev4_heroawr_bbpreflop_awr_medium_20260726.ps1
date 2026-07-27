$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$strongRecord = (
    'models\sourcev4_heroawr_bbpreflop_awr_strong_20260726\' +
    'experiment_record.json'
)
$deadline = (Get-Date).AddHours(2)
while (
    -not (Test-Path -LiteralPath $strongRecord -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $strongRecord -PathType Leaf)) {
    throw 'Timed out waiting for the strong-AWR internal screen'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
        'selected.pt'
    )
).Path
$mimicProxy = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_slumbot_composed_preflopformal100k_e5_' +
        'postflophistory500k_e4_20260726\latest.pt'
    )
).Path
$outputDir = 'models\sourcev4_heroawr_bbpreflop_awr_medium_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "Medium BB-preflop AWR output already exists: $outputDir"
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
    --seed 20260808 `
    --device cuda `
    --epochs 8 `
    --batch-size 2048 `
    --lr 0.0002 `
    --kl-coef 0.5 `
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
    throw 'Medium BB-preflop AWR training failed'
}

$trainingReport = Get-Content -LiteralPath (
    Join-Path $outputDir 'report.json'
) -Raw | ConvertFrom-Json
$mixRows = @(
    foreach ($epoch in $trainingReport.history) {
        $frequencies = @($epoch.predicted_action_frequency)
        $fold = [double]$frequencies[0]
        $call = [double]$frequencies[1]
        $raise = 1.0 - $fold - $call
        [pscustomobject]@{
            name = "epoch$([int]$epoch.epoch)"
            checkpoint = Join-Path $outputDir "epoch_$([int]$epoch.epoch).pt"
            source_kl = [double]$epoch.source_kl
            fold_frequency = $fold
            call_frequency = $call
            raise_frequency = $raise
            target_mix_distance = (
                [math]::Abs($fold - 0.30) +
                [math]::Abs($call - 0.35) +
                [math]::Abs($raise - 0.35)
            )
        }
    }
)
$mixEligible = @(
    $mixRows |
        Where-Object {
            $_.source_kl -ge 0.0005 -and
            $_.source_kl -le 0.50 -and
            $_.fold_frequency -ge 0.20 -and
            $_.fold_frequency -le 0.45 -and
            $_.call_frequency -ge 0.15 -and
            $_.call_frequency -le 0.55 -and
            $_.raise_frequency -ge 0.20 -and
            $_.raise_frequency -le 0.50
        } |
        Sort-Object target_mix_distance |
        Select-Object -First 3
)
if ($mixEligible.Count -eq 0) {
    $mixEligible = @(
        $mixRows |
            Sort-Object source_kl |
            Select-Object -First 3
    )
}

$curveDir = Join-Path $outputDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
$candidatePaths = [ordered]@{ source = $source }
foreach ($row in $mixEligible) {
    $candidatePaths[$row.name] = $row.checkpoint
}
$curve = foreach ($entry in $candidatePaths.GetEnumerator()) {
    $genericJson = Join-Path $curveDir "$($entry.Key).json"
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
        --out-json $genericJson `
        --out-md (Join-Path $curveDir "$($entry.Key).md")
    $probeOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Medium-AWR generic probe failed: $($entry.Key)"
    }
    $generic = Get-Content -LiteralPath $genericJson -Raw | ConvertFrom-Json

    $mimicJson = Join-Path $curveDir "$($entry.Key)_mimic.json"
    $probeOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 2000 `
        --checkpoint-opponent $mimicProxy `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode sample `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260807 `
        --policy-mode greedy `
        --out-json $mimicJson `
        --out-md (Join-Path $curveDir "$($entry.Key)_mimic.md")
    $probeOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Medium-AWR mimic probe failed: $($entry.Key)"
    }
    $mimic = Get-Content -LiteralPath $mimicJson -Raw | ConvertFrom-Json
    [pscustomobject]@{
        name = $entry.Key
        checkpoint = $entry.Value
        mean_bb_per_100 = [double](
            ($generic.results | Measure-Object -Property bb100 -Average).Average
        )
        mimic_proxy_bb_per_100 = [double](
            ($mimic.results | Measure-Object -Property bb100 -Average).Average
        )
        total_hands = [int64]$generic.checkpoint.total_hands
        results = $generic.results
        mimic_results = $mimic.results
    }
}
$sourceRow = $curve | Where-Object name -eq 'source'
$eligible = @(
    $curve |
        Where-Object {
            $_.name -ne 'source' -and
            $_.mean_bb_per_100 -ge ($sourceRow.mean_bb_per_100 - 50.0)
        }
)
$best = $eligible |
    Sort-Object mimic_proxy_bb_per_100 -Descending |
    Select-Object -First 1
$retain = $null -ne $best
$offlineRows = (
    [int64]$trainingReport.train_rows + [int64]$trainingReport.val_rows
)

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A moderate AWR dose can increase profitable BB reraising without the ' +
        'negligible shift of the first run or the extreme shift of strong AWR.'
    )
    material_change = (
        'Dedicated preflop-head AWR with lr=2e-4, KL=0.5 and eight epochs; ' +
        'candidate epochs are chosen by learned BB action mix before fixed probes.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = 0
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = $offlineRows
    training_history = $trainingReport.history
    action_mix_candidates = $mixEligible
    curve = $curve
    selected_checkpoint = if ($retain) { $best.checkpoint } else { $null }
    selected_mean_bb_per_100 = if ($retain) {
        [double]$best.mean_bb_per_100
    } else {
        $null
    }
    selected_mimic_proxy_bb_per_100 = if ($retain) {
        [double]$best.mimic_proxy_bb_per_100
    } else {
        $null
    }
    run_fresh5k = $retain
    decision = if ($retain) { 'RETAIN_AND_SCREEN' } else { 'REJECT' }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $outputDir 'experiment_record.json') `
        -Encoding UTF8
if (-not $retain) { exit 0 }

$selected = Join-Path $outputDir 'selected.pt'
Copy-Item -LiteralPath $best.checkpoint -Destination $selected
$externalDir = (
    'models\bench_sourcev4_heroawr_bbpreflop_awr_medium_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_heroawr_bbpreflop_awr_medium_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Medium BB-preflop AWR fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_bbpreflop_awr_medium' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_heroawr_bbpreflop_awr_medium' `
    -TrainingMethod 'medium-dose BB-only preflop-head historical offline AWR' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples $offlineRows
exit $LASTEXITCODE
