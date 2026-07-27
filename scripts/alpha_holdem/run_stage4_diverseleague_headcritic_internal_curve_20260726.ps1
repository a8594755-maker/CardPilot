$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/stage4_diverseleague_headcritic_1m_20260726/internal_curve"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    @{
        Label = "source_h657k"
        Path = "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt"
    },
    @{
        Label = "new_h263k"
        Path = "models/stage4_diverseleague_headcritic_1m_20260726/checkpoints/checkpoint_iter000008_hands000000262805.pt"
    },
    @{
        Label = "new_h526k"
        Path = "models/stage4_diverseleague_headcritic_1m_20260726/checkpoints/checkpoint_iter000016_hands000000525860.pt"
    },
    @{
        Label = "new_h789k"
        Path = "models/stage4_diverseleague_headcritic_1m_20260726/checkpoints/checkpoint_iter000024_hands000000788927.pt"
    },
    @{
        Label = "new_h1019k"
        Path = "models/stage4_diverseleague_headcritic_1m_20260726/latest.pt"
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
