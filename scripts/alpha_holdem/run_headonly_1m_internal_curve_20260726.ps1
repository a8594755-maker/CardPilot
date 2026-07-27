$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/slumbot_br_preflopv2_mimic_postflop_headonly_1m_20260725/internal_curve"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    @{
        Label = "source"
        Path = "models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt"
    },
    @{
        Label = "h131k"
        Path = "models/slumbot_br_preflopv2_mimic_postflop_headonly_1m_20260725/checkpoints/checkpoint_iter000004_hands000000131257.pt"
    },
    @{
        Label = "h526k"
        Path = "models/slumbot_br_preflopv2_mimic_postflop_headonly_1m_20260725/checkpoints/checkpoint_iter000016_hands000000525260.pt"
    },
    @{
        Label = "h1018k"
        Path = "models/slumbot_br_preflopv2_mimic_postflop_headonly_1m_20260725/latest.pt"
    }
)

foreach ($candidate in $candidates) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidate.Path `
        --hands 500 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --seed 20260726 `
        --policy-mode greedy `
        --out-json "$outDir/$($candidate.Label).json" `
        --out-md "$outDir/$($candidate.Label).md"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
