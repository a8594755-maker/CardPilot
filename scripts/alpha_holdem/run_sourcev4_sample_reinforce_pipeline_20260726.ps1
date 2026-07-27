$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$collectionDir = 'models\collect_sourcev4_sample_training5k_20260726'
$collectionTag = 'bench_v55_sourcev4_sample_training5k_20260726'
$source = 'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt'
$trainDir = 'models\sourcev4_sample5k_reinforce_kl1_20260726'
$curveDir = Join-Path $trainDir 'internal_probe'
$externalDir = 'models\bench_sourcev4_sample5k_reinforce_kl1_pure_fresh5k_20260726'
$deadline = (Get-Date).AddHours(8)

while ((Get-Date) -lt $deadline) {
    $handFiles = @(
        Get-ChildItem -LiteralPath $collectionDir -Filter '*_hands.jsonl' -File -ErrorAction SilentlyContinue
    )
    $hands = 0
    foreach ($handFile in $handFiles) {
        $line = Get-Content -LiteralPath $handFile.FullName -Tail 1
        if ($line) {
            $hands += [int](($line | ConvertFrom-Json).successful_hand)
        }
    }
    if ($handFiles.Count -eq 4 -and $hands -eq 5000) {
        break
    }
    $collector = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'sourcev4_sample_training5k_20260726'
            }
    )
    if ($collector.Count -eq 0 -and $hands -lt 5000) {
        throw "Sample collection exited early at $hands hands"
    }
    Start-Sleep -Seconds 30
}

$dumps = @(
    1..4 | ForEach-Object {
        Join-Path $collectionDir ($collectionTag + ('_part{0}_dump.jsonl' -f $_))
    }
)
if (@($dumps | Where-Object { -not (Test-Path -LiteralPath $_) }).Count -gt 0) {
    throw 'Completed sample collection is missing one or more decision dumps'
}
if (Test-Path -LiteralPath $trainDir) {
    throw "Training output already exists: $trainDir"
}

$trainArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/offline_slumbot_reinforce.py',
    '--source-checkpoint', $source,
    '--dumps'
) + $dumps + @(
    '--out-dir', $trainDir,
    '--obs-version', 'v4',
    '--max-rows', '100000',
    '--min-rows', '2000',
    '--street-min', '0',
    '--street-max', '3',
    '--seed', '20260741',
    '--device', 'cuda',
    '--epochs', '3',
    '--batch-size', '1024',
    '--lr', '0.00001',
    '--weight-decay', '0.00001',
    '--clip-ratio', '0.10',
    '--source-kl-coef', '1.0',
    '--return-clip-bb', '20',
    '--min-bucket-count', '20',
    '--advantage-scale-bb', '5',
    '--advantage-clip', '4',
    '--val-fraction', '0.10'
)
& python @trainArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Offline Slumbot REINFORCE failed'
}

$best = Join-Path $trainDir 'best.pt'
if (-not (Test-Path -LiteralPath $best)) {
    throw 'REINFORCE completed without best.pt'
}
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $best `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260726 `
    --policy-mode greedy `
    --out-json (Join-Path $curveDir 'candidate.json') `
    --out-md (Join-Path $curveDir 'candidate.md')
if ($LASTEXITCODE -ne 0) {
    throw 'REINFORCE internal probe failed'
}

if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $best).Path `
    -Tag 'sourcev4_sample5k_reinforce_kl1_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
