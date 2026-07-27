$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $repo

$trainerPid = 35032
$runDir = Join-Path $repo (
    'models\sourcev4_standard10_bb_only_position_adapter_aggressive10m_' +
    'after10m_20260727'
)
$source = Join-Path $repo (
    'models\sourcev4_standard10_bb_only_position_adapter10m_20260727\latest.pt'
)
$checkpoint700 = Join-Path $runDir (
    'checkpoints\checkpoint_iter000700_hands000023001114.pt'
)
$checkpoint800 = Join-Path $runDir (
    'checkpoints\checkpoint_iter000800_hands000026287477.pt'
)
$checkpoint900Pattern = Join-Path $runDir (
    'checkpoints\checkpoint_iter000900_hands*.pt'
)
$final = Join-Path $runDir 'latest.pt'
$outDir = Join-Path $runDir 'internal_stable_curve_v1_20260727'

if (Get-Process -Id $trainerPid -ErrorAction SilentlyContinue) {
    Wait-Process -Id $trainerPid
}

$checkpoint900Files = @(Get-ChildItem -Path $checkpoint900Pattern -File)
if ($checkpoint900Files.Count -ne 1) {
    throw "Expected exactly one iteration-900 checkpoint, got $($checkpoint900Files.Count)"
}

$required = @($source, $checkpoint700, $checkpoint800, $final)
foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing frozen curve input: $path"
    }
}

$sourceHands = [int64](& python -X utf8 -c (
    'import sys,torch; ' +
    'print(int(torch.load(sys.argv[1],map_location="cpu",weights_only=False)' +
    '.get("total_hands",-1)))'
) $source)
$finalHands = [int64](& python -X utf8 -c (
    'import sys,torch; ' +
    'print(int(torch.load(sys.argv[1],map_location="cpu",weights_only=False)' +
    '.get("total_hands",-1)))'
) $final)
if ($finalHands - $sourceHands -lt 10000000) {
    throw "Training endpoint is short: $($finalHands - $sourceHands) new hands"
}

& python -X utf8 scripts/alpha_holdem/v5_training_curve_eval.py `
    --candidate "bbaggr_source_0m=$source" `
    --candidate "bbaggr_new2p69m=$checkpoint700" `
    --candidate "bbaggr_new5p98m=$checkpoint800" `
    --candidate "bbaggr_new9p2m=$($checkpoint900Files[0].FullName)" `
    --candidate "bbaggr_new10m=$final" `
    --anchor (
        'imitation_teacher=' +
        (Join-Path $repo (
            'models\sourcev4_slumbot_history500k_allstreet_imitation_' +
            'fullnet_20260726\best.pt'
        ))
    ) `
    --anchor (
        'standard10_final=' +
        (Join-Path $repo (
            'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\' +
            'latest.pt'
        ))
    ) `
    --anchor (
        'slumbot_free10m=' +
        (Join-Path $repo (
            'models\slumbot_free_anchor_position10m_20260727\latest.pt'
        ))
    ) `
    --pairs 1024 `
    --seed 2026072709 `
    --device cpu `
    --priority below-normal `
    --torch-threads 2 `
    --torch-interop-threads 1 `
    --out-dir $outDir
if ($LASTEXITCODE -ne 0) {
    throw 'Aggressive BB stable curve failed'
}
