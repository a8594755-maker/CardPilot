$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/stage4_pure_selfplay_policyonly_1m_20260726/internal_curve"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    @{
        Label = "source_h657k"
        Path = "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt"
    },
    @{
        Label = "new_h264k"
        Path = "models/stage4_pure_selfplay_policyonly_1m_20260726/checkpoints/checkpoint_iter000008_hands000000264050.pt"
    },
    @{
        Label = "new_h528k"
        Path = "models/stage4_pure_selfplay_policyonly_1m_20260726/checkpoints/checkpoint_iter000016_hands000000527750.pt"
    },
    @{
        Label = "new_h792k"
        Path = "models/stage4_pure_selfplay_policyonly_1m_20260726/checkpoints/checkpoint_iter000024_hands000000791550.pt"
    },
    @{
        Label = "new_h1022k"
        Path = "models/stage4_pure_selfplay_policyonly_1m_20260726/latest.pt"
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
