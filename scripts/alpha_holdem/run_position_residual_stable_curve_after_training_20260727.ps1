param(
    [Parameter(Mandatory = $true)]
    [string]$RunDir,
    [Parameter(Mandatory = $true)]
    [string]$Source,
    [Parameter(Mandatory = $true)]
    [string]$LabelPrefix,
    [int]$WaitForPid = 0,
    [int64]$ExpectedNewHands = 10000000,
    [int]$Seed = 2026072711
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repo
$resolvedRunDir = (Resolve-Path -LiteralPath $RunDir).Path
$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
$final = Join-Path $resolvedRunDir 'latest.pt'
$outDir = Join-Path $resolvedRunDir 'internal_stable_curve_v1_20260727'

if (
    $WaitForPid -gt 0 -and
    (Get-Process -Id $WaitForPid -ErrorAction SilentlyContinue)
) {
    Wait-Process -Id $WaitForPid
}
if (-not (Test-Path -LiteralPath $final -PathType Leaf)) {
    throw "Missing final checkpoint: $final"
}

$checkpointFiles = @(
    Get-ChildItem -LiteralPath (
        Join-Path $resolvedRunDir 'checkpoints'
    ) -Filter 'checkpoint_*.pt' -File
)
$candidatePaths = @($resolvedSource) + @(
    $checkpointFiles | ForEach-Object { $_.FullName }
) + @($final)

$checkpointRows = @()
foreach ($path in $candidatePaths) {
    $summary = @(
        & python -X utf8 -c (
            'import sys,torch; ' +
            'c=torch.load(sys.argv[1],map_location="cpu",weights_only=False); ' +
            'print(int(c.get("total_hands",-1))); ' +
            'print(int(c.get("iteration",-1)))'
        ) $path
    )
    if ($LASTEXITCODE -ne 0 -or $summary.Count -lt 2) {
        throw "Could not inspect curve input: $path"
    }
    $checkpointRows += [pscustomobject]@{
        Path = (Resolve-Path -LiteralPath $path).Path
        Hands = [int64]$summary[-2]
        Iteration = [int]$summary[-1]
    }
}

$sourceHands = [int64](
    $checkpointRows |
        Where-Object { $_.Path -eq $resolvedSource } |
        Select-Object -First 1 -ExpandProperty Hands
)
$finalHands = [int64](
    $checkpointRows |
        Where-Object { $_.Path -eq (Resolve-Path -LiteralPath $final).Path } |
        Select-Object -First 1 -ExpandProperty Hands
)
if ($finalHands - $sourceHands -lt $ExpectedNewHands) {
    throw (
        "Training endpoint is short: $($finalHands - $sourceHands) new hands; " +
        "expected at least $ExpectedNewHands"
    )
}

$orderedCandidates = @(
    $checkpointRows |
        Where-Object {
            $_.Hands -ge $sourceHands -and $_.Hands -le $finalHands
        } |
        Sort-Object Hands, Path -Unique
)
$arguments = @(
    '-X', 'utf8',
    'scripts/alpha_holdem/v5_training_curve_eval.py'
)
foreach ($row in $orderedCandidates) {
    $delta = [int64]$row.Hands - $sourceHands
    $label = if ($delta -eq 0) {
        "${LabelPrefix}_source_0"
    } elseif ($row.Path -eq (Resolve-Path -LiteralPath $final).Path) {
        "${LabelPrefix}_final_${delta}h"
    } else {
        "${LabelPrefix}_iter$($row.Iteration)_${delta}h"
    }
    $arguments += @('--candidate', "$label=$($row.Path)")
}

$anchorSpecs = @(
    [pscustomobject]@{
        Label = 'lineage_source'
        Path = $resolvedSource
    },
    [pscustomobject]@{
        Label = 'standard10_final'
        Path = Join-Path $repo (
            'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\' +
            'latest.pt'
        )
    },
    [pscustomobject]@{
        Label = 'scaled_teacher'
        Path = Join-Path $repo (
            'models\sourcev4_slumbot_history_allstreet_imitation_' +
            'scale1p25m_20260727\best.pt'
        )
    },
    [pscustomobject]@{
        Label = 'slumbot_free10m'
        Path = Join-Path $repo (
            'models\slumbot_free_anchor_position10m_20260727\latest.pt'
        )
    }
)
$seenAnchors = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($anchor in $anchorSpecs) {
    $anchorPath = (Resolve-Path -LiteralPath $anchor.Path).Path
    if ($seenAnchors.Add($anchorPath)) {
        $arguments += @('--anchor', "$($anchor.Label)=$anchorPath")
    }
}
$arguments += @(
    '--pairs', '1024',
    '--seed', [string]$Seed,
    '--device', 'cpu',
    '--priority', 'below-normal',
    '--torch-threads', '2',
    '--torch-interop-threads', '1',
    '--out-dir', $outDir
)

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Position-residual stable curve failed for $LabelPrefix"
}
