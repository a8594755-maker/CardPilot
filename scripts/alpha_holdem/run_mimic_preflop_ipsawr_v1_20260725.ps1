$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/slumbot_mimic_preflop_ipsawr_v1_20260725"
$roots = @(
    "models/slumbot_stage4_temp25_explore10k_data_20260725",
    "models/slumbot_stage4_temp25_explore4k_data_cont_20260725",
    "models/slumbot_stage4_preflopmixed_temp25_explore20k_data_20260725",
    "models/slumbot_stage4_preflopmixed_temp25_explore5k_cont_20260725",
    "models/slumbot_stage4_preflop_epsilon30_explore5k_20260725"
)

$arguments = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/offline_slumbot_awr.py",
    "--source-checkpoint",
        "models/slumbot_imitation_stage4_onpolicy_v2_20260725/best.pt",
    "--out-dir", $outDir,
    "--roots"
) + $roots + @(
    "--exclude-substring", "__include_20260725__",
    "--obs-version", "v4",
    "--actor", "hero",
    "--street-min", "0",
    "--street-max", "0",
    "--max-rows", "300000",
    "--seed", "2026072596",
    "--device", "cuda",
    "--epochs", "3",
    "--batch-size", "4096",
    "--lr", "0.00002",
    "--weight-decay", "0.00001",
    "--kl-coef", "0.5",
    "--return-clip-bb", "10",
    "--beta-bb", "5",
    "--min-bucket-count", "30",
    "--weight-min", "0.05",
    "--weight-max", "20",
    "--inverse-propensity-power", "1.0",
    "--inverse-propensity-cap", "8.0",
    "--val-fraction", "0.10",
    "--separate-preflop-head-only"
)

& python @arguments
exit $LASTEXITCODE
