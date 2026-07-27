$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$outDir = "models/slumbot_imitation_stage4_onpolicy_v2_20260725"
$stdout = "models/slumbot_imitation_stage4_onpolicy_v2_20260725.stdout.log"
$stderr = "models/slumbot_imitation_stage4_onpolicy_v2_20260725.stderr.log"

$roots = @(
    "models/slumbot_br_ensemble4_stage4fast_combined10k_20260725",
    "models/slumbot_stage4_temp25_explore10k_data_20260725",
    "models/slumbot_stage4_temp25_explore4k_data_cont_20260725",
    "models/slumbot_stage4_flopepsilon30_explore5k_20260725",
    "models/slumbot_stage4_flopepsilon80_explore10k_20260725",
    "models/slumbot_stage4_flopepsilon80_explore10k_rep2_20260725",
    "models/slumbot_stage4_turnepsilon30_explore5k_20260725",
    "models/slumbot_stage4_riverepsilon30_explore5k_20260725",
    "models/slumbot_stage4_preflopmixed_temp25_explore20k_data_20260725",
    "models/slumbot_stage4_preflopmixed_temp25_explore5k_cont_20260725",
    "models/slumbot_stage4_preflop_epsilon30_explore5k_20260725"
)

$argsList = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/offline_slumbot_awr.py",
    "--source-checkpoint", "models/slumbot_imitation_all413_plain_seed61_20260725/best.pt",
    "--out-dir", $outDir,
    "--roots"
) + $roots + @(
    "--exclude-substring", "__no_such_token__",
    "--obs-version", "v4",
    "--actor", "opp",
    "--street-min", "0",
    "--street-max", "3",
    "--max-rows", "300000",
    "--seed", "2026072593",
    "--device", "cuda",
    "--epochs", "6",
    "--batch-size", "4096",
    "--lr", "0.00002",
    "--weight-decay", "0.00001",
    "--kl-coef", "0.05",
    "--return-clip-bb", "0",
    "--decision-risk-power", "0",
    "--val-fraction", "0.10"
)

# offline_slumbot_awr creates the output directory itself.
& python @argsList 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
