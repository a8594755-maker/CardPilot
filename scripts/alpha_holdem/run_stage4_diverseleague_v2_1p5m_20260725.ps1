$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repo

$python = (Get-Command python).Source
$runId = "slumbot_br_stage4_diverseleague_v2_1p5m_20260725"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
$stdout = Join-Path $runDir "train.stdout.log"
$stderr = Join-Path $runDir "train.stderr.log"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$trainArgs = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--device", "cuda",
    "--workers", "28",
    "--hands-per-iter", "32768",
    "--total-hands", "1500000",
    "--reset-hand-counter",
    "--starting-stack", "200",
    "--env-version", "v55v4obs",
    "--norm-layer", "gn",
    "--lr", "3e-6",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0.02",
    "--source-policy-kl-coef", "0.05",
    "--mini-batch-size", "2048",
    "--epsilon", "0.0",
    "--gamma", "0.999",
    "--gae-lambda", "0.95",
    "--delta1", "3.0",
    "--entropy-coef", "0.002",
    "--entropy-floor", "0.0",
    "--fixed-opponent-checkpoints",
        "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
        "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
        "models/slumbot_imitation_seed11b_700k_20260725/best.pt",
        "models/slumbot_imitation_subset_seed22_350k_20260725/best.pt",
        "models/slumbot_imitation_recent14_seed44_300k_20260725/best.pt",
        "models/slumbot_imitation_recent14_risk05_seed45_300k_20260725/best.pt",
        "models/slumbot_imitation_recent15_seed46_300k_20260725/best.pt",
        "models/slumbot_imitation_recent15_risk075_seed47_300k_20260725/best.pt",
    "--self-play-fraction", "0.0",
    "--opponent-assignment", "per-iteration",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "128",
    "--inference-batch-deadline-us", "2000",
    "--archive-checkpoint-every", "8",
    "--save-interval", "4",
    "--max-runtime-seconds", "14400",
    "--resume", "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
    "--allow-resume",
    "--reset-optimizer",
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--out", $out,
    "--seed", "2026072592"
)

& $python @trainArgs 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
