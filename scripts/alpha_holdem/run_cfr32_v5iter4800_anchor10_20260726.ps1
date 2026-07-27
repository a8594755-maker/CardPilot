$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$dataDir = 'data\training\cfr_v55_compact_200bb_flops32_sample05_20260726'
$manifest = Join-Path $dataDir 'manifest.json'
$source = 'models\v5iter4800_preflopraw256_distilled_20260726\latest.pt'
$anchor = 'data\training\source_anchor_v5iter4800_preflopraw256_diverse100k_20260726.pt'
$outDir = 'models\v5iter4800_preflopraw256_cfr32_anchor10_3m_20260726'
$latest = Join-Path $outDir 'latest.pt'

New-Item -ItemType Directory -Path $outDir -Force | Out-Null
while (-not (Test-Path -LiteralPath $manifest)) {
    Write-Host "Waiting for complete CFR32 manifest: $manifest"
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $source)) {
    throw "Missing source checkpoint: $source"
}
if (-not (Test-Path -LiteralPath $anchor)) {
    throw "Missing source anchor: $anchor"
}

$trainArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/distill_cfr_v55_compact.py',
    '--source', $source,
    '--data', $dataDir,
    '--out', $latest,
    '--device', 'cuda',
    '--adapter-hidden', '128',
    '--epochs', '3',
    '--batch-size', '1024',
    '--lr', '0.0001',
    '--source-kl', '1.0',
    '--anchor-features', $anchor,
    '--anchor-kl', '10.0',
    '--residual-l2', '0.0001',
    '--samples-per-epoch', '1000000',
    '--val-fraction', '0.10',
    '--val-split', 'board',
    '--street-weights', '0.005,0.095,0.900',
    '--seed', '20260730'
)
& python @trainArgs 2>&1 | Tee-Object -FilePath (Join-Path $outDir 'train.log')
if ($LASTEXITCODE -ne 0) {
    throw "CFR32 distillation failed with exit code $LASTEXITCODE"
}

$curveDir = Join-Path $outDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
foreach ($epoch in 1..3) {
    $checkpoint = Join-Path $outDir ("latest_epoch{0:D2}.pt" -f $epoch)
    $stem = "epoch{0:D2}" -f $epoch
    $probeArgs = @(
        '-X', 'utf8', '-u',
        'scripts/alpha_holdem/v5_internal_strength_probe.py',
        '--checkpoint', $checkpoint,
        '--hands', '1000',
        '--opponents', 'aggressive', 'call-station', 'random',
        '--max-pool-snapshots', '0',
        '--device', 'cuda',
        '--seed', '20260726',
        '--policy-mode', 'greedy',
        '--out-json', (Join-Path $curveDir "$stem.json"),
        '--out-md', (Join-Path $curveDir "$stem.md")
    )
    & python @probeArgs 2>&1 | Tee-Object -FilePath (Join-Path $curveDir "$stem.log")
    if ($LASTEXITCODE -ne 0) {
        throw "Internal probe failed for $checkpoint"
    }
}
