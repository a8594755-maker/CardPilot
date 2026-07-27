$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/preflopv2_cfr200bb_adapter_board1_272k_20260726/internal_curve_corrected"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$candidates = @(
    @{ Label = "epoch01"; Path = "models/preflopv2_cfr200bb_adapter_board1_272k_20260726/latest_epoch01.pt" },
    @{ Label = "epoch02"; Path = "models/preflopv2_cfr200bb_adapter_board1_272k_20260726/latest_epoch02.pt" },
    @{ Label = "epoch03"; Path = "models/preflopv2_cfr200bb_adapter_board1_272k_20260726/latest_epoch03.pt" },
    @{ Label = "epoch04"; Path = "models/preflopv2_cfr200bb_adapter_board1_272k_20260726/latest_epoch04.pt" }
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
