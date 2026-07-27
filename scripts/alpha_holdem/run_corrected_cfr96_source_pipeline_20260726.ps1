$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$dataDir = 'data\training\cfr_v55_compact_v3_200bb_flops096_balanced_20260726'
$manifestPath = Join-Path $dataDir 'manifest.json'
$outputDir = 'models\sourcev4_corrected_cfr96_anchor10_20260726'
$curveDir = Join-Path $outputDir 'internal_curve'
$externalDir = 'models\bench_sourcev4_corrected_cfr96_selected_pure_fresh5k_20260726'
$deadline = (Get-Date).AddHours(5)

while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $manifestPath) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        $boardFiles = @(
            Get-ChildItem -LiteralPath $dataDir -Filter 'flop_*.jsonl' -File
        )
        if (
            $manifest.config -eq 'pipeline_srp_v3_200bb' -and
            [int]$manifest.processedFlops -eq 96 -and
            $boardFiles.Count -eq 96
        ) {
            break
        }
    }
    $converter = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'cfr-to-training-data.ts' -and
                $_.CommandLine -match 'cfr_v55_compact_v3_200bb_flops096_balanced_20260726'
            }
    )
    if ($converter.Count -eq 0) {
        throw 'Corrected CFR96 converter exited before a valid manifest'
    }
    Start-Sleep -Seconds 30
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw 'Timed out waiting for the corrected CFR96 manifest'
}
if (Test-Path -LiteralPath $outputDir) {
    throw "Training output already exists: $outputDir"
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

$trainArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/distill_cfr_v55_compact.py',
    '--source', 'models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt',
    '--data', $dataDir,
    '--out', (Join-Path $outputDir 'latest.pt'),
    '--device', 'cuda',
    '--adapter-hidden', '128',
    '--epochs', '3',
    '--batch-size', '1024',
    '--lr', '0.0001',
    '--source-kl', '1.0',
    '--anchor-features', 'data/training/source_anchor_v4_diverse100k_20260726.pt',
    '--anchor-kl', '10.0',
    '--residual-l2', '0.0001',
    '--samples-per-epoch', '750000',
    '--val-fraction', '0.125',
    '--val-split', 'board',
    '--street-weights', '0.3333333333,0.3333333333,0.3333333334',
    '--seed', '20260742'
)
& python @trainArgs 2>&1 | Tee-Object -FilePath (Join-Path $outputDir 'train.log')
if ($LASTEXITCODE -ne 0) {
    throw 'Corrected CFR96 source distillation failed'
}

New-Item -ItemType Directory -Path $curveDir | Out-Null
foreach ($epoch in 1..3) {
    $checkpoint = Join-Path $outputDir ('latest_epoch{0:D2}.pt' -f $epoch)
    $stem = 'epoch{0:D2}' -f $epoch
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $checkpoint `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260726 `
        --policy-mode greedy `
        --out-json (Join-Path $curveDir "$stem.json") `
        --out-md (Join-Path $curveDir "$stem.md") `
        2>&1 | Tee-Object -FilePath (Join-Path $curveDir "$stem.log")
    if ($LASTEXITCODE -ne 0) {
        throw "Corrected CFR96 internal probe failed for epoch $epoch"
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
    throw 'Corrected CFR96 curve did not produce three ranked epochs'
}
$bestEpoch = $ranked[0].Epoch
$best = Join-Path $outputDir ('latest_epoch{0:D2}.pt' -f $bestEpoch)
Copy-Item -LiteralPath $best -Destination (Join-Path $outputDir 'selected.pt')
$ranked |
    ConvertTo-Json |
    Set-Content -LiteralPath (Join-Path $outputDir 'selection.json') -Encoding UTF8

if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath (Join-Path $outputDir 'selected.pt')).Path `
    -Tag 'sourcev4_corrected_cfr96_selected_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
