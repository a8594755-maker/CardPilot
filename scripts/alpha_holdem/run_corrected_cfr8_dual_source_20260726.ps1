$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$conversionDir = 'data\training\cfr_v55_compact_v3_200bb_flops096_balanced_20260726'
$conversionLog = 'reports\cfr_v55_compact_v3_200bb_flops096_balanced_20260726.log'
$snapshotDir = 'data\training\cfr_v55_compact_v3_200bb_first8_balanced_20260726'

if (Test-Path -LiteralPath $snapshotDir) {
    $snapshotManifestPath = Join-Path $snapshotDir 'manifest.json'
    if (-not (Test-Path -LiteralPath $snapshotManifestPath)) {
        throw "Existing snapshot has no manifest: $snapshotDir"
    }
    $existingManifest = Get-Content -LiteralPath $snapshotManifestPath -Raw | ConvertFrom-Json
    $snapshotBoards = @(Get-ChildItem -LiteralPath $snapshotDir -Filter 'flop_*.jsonl' -File)
    if ($existingManifest.config -ne 'pipeline_srp_v3_200bb' -or
        [int]$existingManifest.processedFlops -ne 8 -or
        $snapshotBoards.Count -ne 8) {
        throw "Existing snapshot does not satisfy the corrected 200bb first-eight contract: $snapshotDir"
    }
} else {
    $deadline = (Get-Date).AddHours(2)
    $completed = @()
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $conversionLog) {
            $completed = @(
                Get-Content -LiteralPath $conversionLog |
                    ForEach-Object {
                        if ($_ -match 'Flop\s+(\d+):\s+(\d+)\s+samples') {
                            [PSCustomObject]@{
                                BoardId = [int]$Matches[1]
                                Samples = [int]$Matches[2]
                            }
                        }
                    } |
                    Select-Object -First 8
            )
        }
        if ($completed.Count -ge 8) {
            break
        }
        Start-Sleep -Seconds 15
    }
    if ($completed.Count -lt 8) {
        throw "Timed out waiting for eight completed corrected CFR boards"
    }

    New-Item -ItemType Directory -Path $snapshotDir | Out-Null
    foreach ($row in $completed) {
        $name = 'flop_{0:D4}.jsonl' -f $row.BoardId
        $source = Join-Path $conversionDir $name
        if (-not (Test-Path -LiteralPath $source)) {
            throw "Completed board output is missing: $source"
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $snapshotDir $name)
    }

    $snapshotManifest = [ordered]@{
        status = 'COMPLETE_FIRST8_SNAPSHOT'
        config = 'pipeline_srp_v3_200bb'
        sourceConfigs = @('pipeline_srp_v3_200bb')
        sourceStacks = @('200bb')
        flopIds = @($completed | ForEach-Object BoardId)
        totalSamples = [int](($completed | Measure-Object Samples -Sum).Sum)
        processedFlops = 8
        sourceConversionDir = $conversionDir
        generatedAt = (Get-Date).ToUniversalTime().ToString('o')
    }
    $snapshotManifest |
        ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath (Join-Path $snapshotDir 'manifest.json') -Encoding UTF8
}

$experiments = @(
    [ordered]@{
        Name = 'v4'
        Source = 'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt'
        Anchor = 'data\training\source_anchor_v4_diverse100k_20260726.pt'
        OutputDir = 'models\sourcev4_corrected_cfr8_anchor10_c1_20260726'
        Seed = '20260732'
    },
    [ordered]@{
        Name = 'v55'
        Source = 'models\v5iter4800_preflopraw256_distilled_20260726\latest.pt'
        Anchor = 'data\training\source_anchor_v5iter4800_preflopraw256_diverse100k_20260726.pt'
        OutputDir = 'models\v5iter4800_preflopraw256_corrected_cfr8_anchor10_c1_20260726'
        Seed = '20260733'
    }
)

foreach ($experiment in $experiments) {
    if (Test-Path -LiteralPath $experiment.OutputDir) {
        throw "Experiment output already exists: $($experiment.OutputDir)"
    }
    New-Item -ItemType Directory -Path $experiment.OutputDir | Out-Null
    $latest = Join-Path $experiment.OutputDir 'latest.pt'
    $trainLog = Join-Path $experiment.OutputDir 'train.log'
    $trainArgs = @(
        '-X', 'utf8', '-u',
        'scripts/alpha_holdem/distill_cfr_v55_compact.py',
        '--source', $experiment.Source,
        '--data', $snapshotDir,
        '--out', $latest,
        '--device', 'cuda',
        '--adapter-hidden', '128',
        '--epochs', '3',
        '--batch-size', '1024',
        '--lr', '0.0001',
        '--source-kl', '1.0',
        '--anchor-features', $experiment.Anchor,
        '--anchor-kl', '10.0',
        '--residual-l2', '0.0001',
        '--samples-per-epoch', '250000',
        '--val-fraction', '0.125',
        '--val-split', 'board',
        '--street-weights', '0.3333333333,0.3333333333,0.3333333334',
        '--seed', $experiment.Seed
    )
    & python @trainArgs 2>&1 | Tee-Object -FilePath $trainLog
    if ($LASTEXITCODE -ne 0) {
        throw "Corrected CFR8 distillation failed for $($experiment.Name)"
    }

    $curveDir = Join-Path $experiment.OutputDir 'internal_curve'
    New-Item -ItemType Directory -Path $curveDir | Out-Null
    foreach ($epoch in 1..3) {
        $checkpoint = Join-Path $experiment.OutputDir ('latest_epoch{0:D2}.pt' -f $epoch)
        $stem = 'epoch{0:D2}' -f $epoch
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
}
