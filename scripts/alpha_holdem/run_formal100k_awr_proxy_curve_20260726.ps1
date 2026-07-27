$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$modelDir = 'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726'
$selection = Join-Path $modelDir 'selection.json'
$proxy = 'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt'
$curveDir = Join-Path $modelDir 'proxy_curve'
$deadline = (Get-Date).AddHours(2)

while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $selection) {
        break
    }
    $pipeline = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'formal100k_postflop_awr_adapter256_mappingfix_20260726'
            }
    )
    if ($pipeline.Count -eq 0) {
        throw 'Formal100k AWR pipeline exited before selection'
    }
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $selection)) {
    throw 'Timed out waiting for formal100k AWR selection'
}

New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
foreach ($epoch in 1..3) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint (Join-Path $modelDir "epoch_$epoch.pt") `
        --hands 1000 `
        --opponents aggressive `
        --checkpoint-opponent $proxy `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode greedy `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260750 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "epoch$epoch.json") `
        --out-md (Join-Path $curveDir "epoch$epoch.md")
    if ($LASTEXITCODE -ne 0) {
        throw "AWR proxy probe failed for epoch $epoch"
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
