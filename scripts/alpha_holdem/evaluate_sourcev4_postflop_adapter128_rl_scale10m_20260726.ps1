$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$trainLog = 'reports\sourcev4_postflop_adapter128_rl_scale10m_20260726.stdout.log'
$run = 'models\sourcev4_postflop_adapter128_rl_scale10m_20260726'
$deadline = (Get-Date).AddHours(7)
while ((Get-Date) -lt $deadline) {
    if (
        (Test-Path -LiteralPath $trainLog) -and
        (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
    ) {
        break
    }
    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq 'python.exe' -and
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_scale10m_20260726'
            }
    )
    if ($trainer.Count -eq 0 -and (Test-Path -LiteralPath $trainLog)) {
        throw 'Scale-10M trainer exited without completion'
    }
    Start-Sleep -Seconds 30
}
if (
    -not (Test-Path -LiteralPath $trainLog) -or
    -not (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
) {
    throw 'Timed out waiting for scale-10M training'
}

$curve = Join-Path $run 'proxy_curve'
New-Item -ItemType Directory -Path $curve -Force | Out-Null
$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$source = 'models\sourcev4_postflop_adapter128_rl_conservative2m_20260726\latest.pt'

$candidateSpecs = @(
    [PSCustomObject]@{ label = 'source_2m'; path = $source },
    [PSCustomObject]@{ label = 'iter175'; pattern = 'checkpoint_iter000175_*.pt' },
    [PSCustomObject]@{ label = 'iter225'; pattern = 'checkpoint_iter000225_*.pt' },
    [PSCustomObject]@{ label = 'iter275'; pattern = 'checkpoint_iter000275_*.pt' },
    [PSCustomObject]@{ label = 'iter325'; pattern = 'checkpoint_iter000325_*.pt' },
    [PSCustomObject]@{ label = 'final_10m'; path = (Join-Path $run 'latest.pt') }
)
$candidates = foreach ($spec in $candidateSpecs) {
    $path = $spec.path
    if (-not $path) {
        $match = @(
            Get-ChildItem -LiteralPath (Join-Path $run 'checkpoints') -Filter $spec.pattern
        )
        if ($match.Count -ne 1) {
            throw "Expected one checkpoint for $($spec.label), found $($match.Count)"
        }
        $path = $match[0].FullName
    }
    [PSCustomObject]@{ label = $spec.label; path = $path }
}

$curveRows = foreach ($candidate in $candidates) {
    $json = Join-Path $curve ($candidate.label + '_proxy1000.json')
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidate.path `
        --hands 1000 `
        --opponents aggressive `
        --checkpoint-opponent $proxy `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode greedy `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260760 `
        --policy-mode greedy `
        --out-json $json `
        --out-md (Join-Path $curve ($candidate.label + '_proxy1000.md')) |
        Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Scale-10M proxy curve failed for $($candidate.label)"
    }
    $result = Get-Content -Raw -LiteralPath $json | ConvertFrom-Json
    [PSCustomObject]@{
        label = $candidate.label
        checkpoint = (Resolve-Path -LiteralPath $candidate.path).Path
        checkpoint_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $candidate.path).Hash.ToLowerInvariant()
        total_hands = [int64]$result.checkpoint.total_hands
        bb100 = [double]$result.results[0].bb100
        ci95 = [double]$result.results[0].ci95_bb100
    }
}
$sourceCurveRow = @($curveRows | Where-Object { $_.label -eq 'source_2m' })[0]
$finalCurveRow = @($curveRows | Where-Object { $_.label -eq 'final_10m' })[0]
$rawTrainedBest = $curveRows |
    Where-Object { $_.label -ne 'source_2m' } |
    Sort-Object bb100 -Descending |
    Select-Object -First 1
$curveBest = if (
    [double]$finalCurveRow.bb100 -ge ([double]$rawTrainedBest.bb100 - 5.0)
) {
    $finalCurveRow
} else {
    $rawTrainedBest
}
$runNewTrainingHands = (
    [int64]$finalCurveRow.total_hands - [int64]$sourceCurveRow.total_hands
)
$selectedNewTrainingHands = (
    [int64]$curveBest.total_hands - [int64]$sourceCurveRow.total_hands
)
[PSCustomObject]@{
    seed = 20260760
    hands_per_candidate = 1000
    rows = @($curveRows)
    raw_best_new_checkpoint = $rawTrainedBest
    selected = $curveBest
    selection_rule = 'Prefer final_10m when it is within 5 bb/100 of the best new checkpoint; otherwise use the best new checkpoint. source_2m is a comparator only.'
    interpretation = 'Internal Slumbot-imitation proxy curve only.'
} |
    ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $curve 'summary.json') -Encoding UTF8

$selected = $curveBest.checkpoint
$selectedProbe = Join-Path $curve 'selected_proxy5000.json'
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $selected `
    --hands 5000 `
    --opponents aggressive `
    --checkpoint-opponent $proxy `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode greedy `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260749 `
    --policy-mode greedy `
    --out-json $selectedProbe `
    --out-md (Join-Path $curve 'selected_proxy5000.md') |
    Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Scale-10M selected standalone proxy evaluation failed'
}

$composedDir = 'models\sourcev4_composed_preflopformal100k_e5_postflopadapter128_rl_scale10m_20260726'
$composed = Join-Path $composedDir 'latest.pt'
& python -X utf8 -u scripts/alpha_holdem/compose_preflop_postflop_checkpoint.py `
    --source 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt' `
    --preflop 'models/sourcev4_slumbot_formal100k_preflop_imitation_head_lr3e4_kl01_mappingfix_20260726/epoch_5.pt' `
    --postflop $selected `
    --out $composed
if ($LASTEXITCODE -ne 0) {
    throw 'Scale-10M composition failed'
}

$composedProbe = Join-Path $curve 'composed_proxy5000.json'
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $composed `
    --hands 5000 `
    --opponents aggressive `
    --checkpoint-opponent $proxy `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode greedy `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260749 `
    --policy-mode greedy `
    --out-json $composedProbe `
    --out-md (Join-Path $curve 'composed_proxy5000.md') |
    Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Scale-10M composed proxy evaluation failed'
}

$standaloneResult = Get-Content -Raw -LiteralPath $selectedProbe | ConvertFrom-Json
$composedResult = Get-Content -Raw -LiteralPath $composedProbe | ConvertFrom-Json
$standaloneBB100 = [double]$standaloneResult.results[0].bb100
$composedBB100 = [double]$composedResult.results[0].bb100
$externalCheckpoint = if (
    $composedBB100 -ge ($standaloneBB100 + 5.0)
) {
    $composed
} else {
    $selected
}
$externalKind = if ($externalCheckpoint -eq $composed) { 'composed' } else { 'standalone' }
$externalBB100 = if ($externalKind -eq 'composed') {
    $composedBB100
} else {
    $standaloneBB100
}
$decision = [PSCustomObject]@{
    hypothesis = 'Scaling conservative postflop self-play from 2M to 10M may improve the stable proxy and external policy.'
    source_checkpoint = (Resolve-Path -LiteralPath $source).Path
    new_training_hands_target = 8000000
    run_new_training_hands_actual = $runNewTrainingHands
    selected_checkpoint_new_training_hands = $selectedNewTrainingHands
    curve_selected_label = $curveBest.label
    curve_selected_checkpoint = $curveBest.checkpoint
    standalone_bb100 = $standaloneBB100
    standalone_ci95 = [double]$standaloneResult.results[0].ci95_bb100
    composed_bb100 = $composedBB100
    composed_ci95 = [double]$composedResult.results[0].ci95_bb100
    selected_kind = $externalKind
    selected_checkpoint = (Resolve-Path -LiteralPath $externalCheckpoint).Path
    selected_checkpoint_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $externalCheckpoint).Hash.ToLowerInvariant()
    selected_bb100 = $externalBB100
    baseline_proxy_bb100 = 32.2362
    launch_external = $true
    external_selection_reason = 'A complete behavior-changing scale milestone requires one fresh external screen. The final checkpoint is preferred over noisy near-ties, and composition must beat standalone by at least 5 bb/100 on the same-seed proxy.'
}
$decision |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $run 'external_decision.json') -Encoding UTF8
if (-not $decision.launch_external) {
    exit 0
}

$externalDir = 'models\bench_sourcev4_postflop_adapter128_rl_scale10m_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $externalCheckpoint).Path `
    -Tag 'sourcev4_postflop_adapter128_rl_scale10m_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Scale-10M selected fresh5k failed'
}
$offlineSamples = if ($externalKind -eq 'composed') { 93034 } else { 0 }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate "sourcev4_postflop_adapter128_rl_scale10m_$externalKind" `
    -QuickDir $externalDir `
    -SourcePolicy $externalCheckpoint `
    -OutputStem "sourcev4_postflop_adapter128_rl_scale10m_$externalKind" `
    -TrainingMethod 'conservative postflop adapter PPO selected from the 2M-to-10M learning curve' `
    -NewTrainingHands $selectedNewTrainingHands `
    -InheritedLineageTrainingHands 3449509 `
    -OfflineDecisionSamples $offlineSamples
exit $LASTEXITCODE
