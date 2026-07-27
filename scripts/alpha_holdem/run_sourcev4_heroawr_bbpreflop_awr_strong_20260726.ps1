$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Avoid adding a fourth concurrent GPU optimizer.  Start as soon as the short
# GAE comparison releases its slot.
$waitPattern = 'sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726'
$deadline = (Get-Date).AddHours(2)
while ((Get-Date) -lt $deadline) {
    $trainers = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq 'python.exe' -and
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match $waitPattern
            }
    )
    if ($trainers.Count -eq 0) { break }
    Start-Sleep -Seconds 20
}
if ((Get-Date) -ge $deadline) {
    throw 'Timed out waiting for the GAE comparison trainer'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
        'selected.pt'
    )
).Path
$outputDir = 'models\sourcev4_heroawr_bbpreflop_awr_strong_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "Strong BB-preflop AWR output already exists: $outputDir"
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
    --seed 20260805 `
    --device cuda `
    --epochs 8 `
    --batch-size 2048 `
    --lr 0.001 `
    --kl-coef 0.1 `
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
    throw 'Strong BB-preflop AWR training failed'
}

$curveDir = Join-Path $outputDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
$mimicProxy = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_slumbot_composed_preflopformal100k_e5_' +
        'postflophistory500k_e4_20260726\latest.pt'
    )
).Path
$candidates = [ordered]@{
    source = $source
    epoch1 = (Join-Path $outputDir 'epoch_1.pt')
    epoch2 = (Join-Path $outputDir 'epoch_2.pt')
    epoch4 = (Join-Path $outputDir 'epoch_4.pt')
    epoch6 = (Join-Path $outputDir 'epoch_6.pt')
    epoch8 = (Join-Path $outputDir 'epoch_8.pt')
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
        throw "Strong BB-preflop AWR internal probe failed: $($entry.Key)"
    }
    $probe = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
    $mimicJson = Join-Path $curveDir "$($entry.Key)_mimic.json"
    $mimicOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 2000 `
        --checkpoint-opponent $mimicProxy `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode greedy `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260807 `
        --policy-mode greedy `
        --out-json $mimicJson `
        --out-md (Join-Path $curveDir "$($entry.Key)_mimic.md")
    $mimicOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Strong BB-preflop mimic probe failed: $($entry.Key)"
    }
    $mimicProbe = Get-Content -LiteralPath $mimicJson -Raw | ConvertFrom-Json
    [pscustomobject]@{
        name = $entry.Key
        checkpoint = $entry.Value
        mean_bb_per_100 = [double](
            ($probe.results | Measure-Object -Property bb100 -Average).Average
        )
        mimic_proxy_bb_per_100 = [double](
            ($mimicProbe.results | Measure-Object -Property bb100 -Average).Average
        )
        total_hands = [int64]$probe.checkpoint.total_hands
        results = $probe.results
        mimic_results = $mimicProbe.results
    }
}

$sourceRow = $rows | Where-Object name -eq 'source'
$trainingReport = Get-Content -LiteralPath (
    Join-Path $outputDir 'report.json'
) -Raw | ConvertFrom-Json
$eligibleNames = @(
    $trainingReport.history |
        Where-Object {
            [double]$_.source_kl -ge 0.001 -and
            [double]$_.source_kl -le 0.20
        } |
        ForEach-Object { "epoch$([int]$_.epoch)" }
)
$eligible = @(
    $rows |
        Where-Object {
            $_.name -ne 'source' -and
            $eligibleNames -contains $_.name -and
            [double]$_.mean_bb_per_100 -ge (
                [double]$sourceRow.mean_bb_per_100 - 50.0
            )
        }
)
if ($eligible.Count -eq 0) {
    $eligible = @(
        $rows |
            Where-Object {
                $_.name -ne 'source' -and
                [double]$_.mean_bb_per_100 -ge (
                    [double]$sourceRow.mean_bb_per_100 - 50.0
                )
            }
    )
}
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
        'The prior BB-preflop AWR update was too weak to change greedy play; ' +
        'a moderate learned head shift can improve BB defense without changing ' +
        'postflop tensors.'
    )
    material_change = (
        'Dedicated preflop-head AWR learning rate 5e-5 to 1e-3, KL coefficient ' +
        '1.0 to 0.1, and 3 to 8 epochs on the same historical BB corpus.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = 0
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = $offlineRows
    curve = $rows
    training_history = $trainingReport.history
    selection_rule = (
        'Highest learned-Slumbot-mimic score among sampled epochs with source ' +
        'KL in [0.001,0.20] and generic internal mean >= source-50; guarded ' +
        'fallback uses the same generic internal floor.'
    )
    selected_checkpoint = if ($retain) { $best.checkpoint } else { $null }
    selected_mean_bb_per_100 = if ($retain) {
        [double]$best.mean_bb_per_100
    } else {
        $null
    }
    source_mean_bb_per_100 = [double]$sourceRow.mean_bb_per_100
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
    'models\bench_sourcev4_heroawr_bbpreflop_awr_strong_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_heroawr_bbpreflop_awr_strong_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Strong BB-preflop AWR fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_bbpreflop_awr_strong' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_heroawr_bbpreflop_awr_strong' `
    -TrainingMethod 'stronger BB-only preflop-head historical offline AWR' `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples $offlineRows
exit $LASTEXITCODE
