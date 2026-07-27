$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$trainLog = 'reports\sourcev4_postflop_adapter128_rl_conservative2m_20260726.stdout.log'
$postflop = 'models\sourcev4_postflop_adapter128_rl_conservative2m_20260726\latest.pt'
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
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_conservative2m_20260726'
            }
    )
    if ($trainer.Count -eq 0 -and (Test-Path -LiteralPath $trainLog)) {
        throw 'Conservative 2M trainer exited without completion'
    }
    Start-Sleep -Seconds 20
}
if (
    -not (Test-Path -LiteralPath $trainLog) -or
    -not (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
) {
    throw 'Timed out waiting for conservative 2M training'
}

$composedDir = 'models\sourcev4_composed_preflopformal100k_e5_postflopadapter128_rl2m_20260726'
$composed = Join-Path $composedDir 'latest.pt'
& python -X utf8 -u scripts/alpha_holdem/compose_preflop_postflop_checkpoint.py `
    --source 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt' `
    --preflop 'models/sourcev4_slumbot_formal100k_preflop_imitation_head_lr3e4_kl01_mappingfix_20260726/epoch_5.pt' `
    --postflop $postflop `
    --out $composed
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative 2M composition failed'
}

$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$postflopProxyResult = Join-Path $composedDir 'postflop_only_proxy5000.json'
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $postflop `
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
    --out-json $postflopProxyResult `
    --out-md (Join-Path $composedDir 'postflop_only_proxy5000.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative 2M postflop-only proxy evaluation failed'
}

$composedProxyResult = Join-Path $composedDir 'composed_proxy5000.json'
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
    --out-json $composedProxyResult `
    --out-md (Join-Path $composedDir 'composed_proxy5000.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative 2M composed proxy evaluation failed'
}

$postflopResult = Get-Content -LiteralPath $postflopProxyResult -Raw | ConvertFrom-Json
$composedResult = Get-Content -LiteralPath $composedProxyResult -Raw | ConvertFrom-Json
$postflopBB100 = [double]$postflopResult.results[0].bb100
$composedBB100 = [double]$composedResult.results[0].bb100
$selected = if ($composedBB100 -gt $postflopBB100) { $composed } else { $postflop }
$selectedKind = if ($selected -eq $composed) { 'composed_preflop_e5_postflop_2m' } else { 'postflop_2m_only' }
$selectedBB100 = [math]::Max($postflopBB100, $composedBB100)
$decision = [PSCustomObject]@{
    baseline_bb100 = 31.4362
    postflop_only_bb100 = $postflopBB100
    postflop_only_ci95 = [double]$postflopResult.results[0].ci95_bb100
    composed_bb100 = $composedBB100
    composed_ci95 = [double]$composedResult.results[0].ci95_bb100
    selected_kind = $selectedKind
    selected_checkpoint = (Resolve-Path -LiteralPath $selected).Path
    selected_checkpoint_sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $selected).Hash.ToLowerInvariant()
    selected_bb100 = $selectedBB100
    external = $selectedBB100 -gt 31.4362
}
$decision |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $composedDir 'external_decision.json') -Encoding UTF8
if (-not $decision.external) {
    exit 0
}

$externalDir = 'models\bench_sourcev4_postflop_adapter128_rl_conservative2m_selected_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_postflop_adapter128_rl_conservative2m_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
