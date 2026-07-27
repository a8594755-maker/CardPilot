$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/preflopv2_postflop_headcritic_mixedleague_1m_20260726/internal_curve"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    @{
        Label = "source_h262k"
        Path = "models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt"
    },
    @{
        Label = "new_h263k"
        Path = "models/preflopv2_postflop_headcritic_mixedleague_1m_20260726/checkpoints/checkpoint_iter000008_hands000000262861.pt"
    },
    @{
        Label = "new_h526k"
        Path = "models/preflopv2_postflop_headcritic_mixedleague_1m_20260726/checkpoints/checkpoint_iter000016_hands000000525576.pt"
    },
    @{
        Label = "new_h788k"
        Path = "models/preflopv2_postflop_headcritic_mixedleague_1m_20260726/checkpoints/checkpoint_iter000024_hands000000788036.pt"
    },
    @{
        Label = "new_h1018k"
        Path = "models/preflopv2_postflop_headcritic_mixedleague_1m_20260726/latest.pt"
    }
)

foreach ($candidate in $candidates) {
    & python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $candidate.Path `
        --hands 1000 `
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
