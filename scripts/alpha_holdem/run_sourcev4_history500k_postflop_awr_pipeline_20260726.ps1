$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$priorResult = 'models\sourcev4_composed_preflopformal100k_e5_postflopawrformal100k_e1_20260726\proxy5000.json'
$deadline = (Get-Date).AddHours(2)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $priorResult) {
        break
    }
    $prior = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'run_composed_awr_proxy_and_external_20260726'
            }
    )
    if ($prior.Count -eq 0) {
        throw 'Composed AWR proxy pipeline exited without a result'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $priorResult)) {
    throw 'Timed out waiting for composed AWR proxy result'
}

$outputDir = 'models\sourcev4_slumbot_history500k_postflop_awr_adapter256_mappingfix_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "Historical AWR output already exists: $outputDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt' `
    --out-dir $outputDir `
    --roots models `
    --exclude-substring '20260726' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 1 `
    --street-max 3 `
    --max-rows 500000 `
    --min-rows 50000 `
    --seed 20260752 `
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
    throw 'Historical postflop AWR training failed'
}

$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$curveDir = Join-Path $outputDir 'proxy_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
foreach ($epoch in 1..3) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint (Join-Path $outputDir "epoch_$epoch.pt") `
        --hands 1000 `
        --opponents aggressive `
        --checkpoint-opponent $proxy `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode greedy `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260753 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "epoch$epoch.json") `
        --out-md (Join-Path $curveDir "epoch$epoch.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Historical AWR proxy probe failed for epoch $epoch"
    }
}

$ranked = @(
    Get-ChildItem -LiteralPath $curveDir -Filter 'epoch*.json' -File |
        ForEach-Object {
            $probe = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            [PSCustomObject]@{
                Epoch = [int]($_.BaseName -replace 'epoch', '')
                BB100 = [double]$probe.results[0].bb100
                CI95 = [double]$probe.results[0].ci95_bb100
            }
        } |
        Sort-Object BB100 -Descending
)
$ranked |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $curveDir 'selection.json') -Encoding UTF8

$bestEpoch = $ranked[0].Epoch
$best = Join-Path $outputDir "epoch_$bestEpoch.pt"
Copy-Item -LiteralPath $best -Destination (Join-Path $outputDir 'selected.pt')
if ([double]$ranked[0].BB100 -le 0) {
    exit 0
}

$externalDir = 'models\bench_sourcev4_slumbot_history500k_postflop_awr_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $best).Path `
    -Tag 'sourcev4_slumbot_history500k_postflop_awr_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
