$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Wait for the fast PPO candidate's proxy-opponent learning curve to finish.
# That scheduler writes this result only after its GPU work is complete.
$priorProbe = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\proxy_curve\slumbot_imitation_proxy.json'
$priorDeadline = (Get-Date).AddHours(7)
while ((Get-Date) -lt $priorDeadline) {
    if (Test-Path -LiteralPath $priorProbe) {
        break
    }
    $prior = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_fast1m_20260726'
            }
    )
    if ($prior.Count -eq 0) {
        throw 'Fast PPO proxy-curve pipeline exited before its result'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $priorProbe)) {
    throw 'Timed out waiting for fast PPO proxy curve'
}

$outputDir = 'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726'
if (Test-Path -LiteralPath $outputDir) {
    throw "AWR output already exists: $outputDir"
}

& python -X utf8 -u scripts/alpha_holdem/offline_slumbot_awr.py `
    --source-checkpoint 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt' `
    --out-dir $outputDir `
    --roots models `
    --include-substring 'rollback_r1_20260708_iter15300_251M_formal100k' `
    --exclude-substring '__no_path_matches_this_token__' `
    --obs-version v4 `
    --raise-action-mapping auto `
    --actor opp `
    --street-min 1 `
    --street-max 3 `
    --max-rows 500000 `
    --min-rows 50000 `
    --seed 20260747 `
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
    throw 'Formal100k postflop AWR training failed'
}

$curveDir = Join-Path $outputDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
foreach ($epoch in 1..3) {
    $checkpoint = Join-Path $outputDir "epoch_$epoch.pt"
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $checkpoint `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260726 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "epoch$epoch.json") `
        --out-md (Join-Path $curveDir "epoch$epoch.md")
    if ($LASTEXITCODE -ne 0) {
        throw "Formal100k AWR internal probe failed for epoch $epoch"
    }
}

$ranked = @(
    Get-ChildItem -LiteralPath $curveDir -Filter 'epoch*.json' -File |
        ForEach-Object {
            $probe = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            [PSCustomObject]@{
                Epoch = [int]($_.BaseName -replace 'epoch', '')
                Mean = [double](($probe.results | Measure-Object -Property bb100 -Average).Average)
            }
        } |
        Sort-Object Mean -Descending
)
if ($ranked.Count -ne 3) {
    throw 'Formal100k AWR curve did not produce three ranked epochs'
}
$bestEpoch = $ranked[0].Epoch
$best = Join-Path $outputDir "epoch_$bestEpoch.pt"
Copy-Item -LiteralPath $best -Destination (Join-Path $outputDir 'selected.pt')
$ranked |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $outputDir 'selection.json') -Encoding UTF8

$externalDir = 'models\bench_sourcev4_slumbot_formal100k_postflop_awr_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath (Join-Path $outputDir 'selected.pt')).Path `
    -Tag 'sourcev4_slumbot_formal100k_postflop_awr_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
