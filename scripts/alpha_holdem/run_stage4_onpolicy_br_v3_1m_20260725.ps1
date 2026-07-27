$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "slumbot_br_stage4_onpolicy_v3_1m_20260725"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
$stdout = Join-Path $runDir "train.stdout.log"
$stderr = Join-Path $runDir "train.stderr.log"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$trainArgs = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--device", "cuda",
    "--workers", "20",
    "--hands-per-iter", "32768",
    "--total-hands", "1000000",
    "--reset-hand-counter",
    "--starting-stack", "200",
    "--env-version", "v55v4obs",
    "--norm-layer", "gn",
    "--lr", "1e-6",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0.01",
    "--source-policy-kl-coef", "0.5",
    "--mini-batch-size", "2048",
    "--epsilon", "0.0",
    "--gamma", "0.999",
    "--gae-lambda", "1.0",
    "--delta1", "3.0",
    "--value-coef", "0.25",
    "--entropy-coef", "0.001",
    "--entropy-floor", "0.0",
    "--fixed-opponent-checkpoints",
        "models/slumbot_imitation_stage4_onpolicy_v2_20260725/best.pt",
        "models/slumbot_imitation_all413_plain_seed61_20260725/best.pt",
        "models/slumbot_imitation_all413_risk05_seed62_20260725/best.pt",
    "--self-play-fraction", "0.0",
    "--opponent-assignment", "per-iteration",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "96",
    "--inference-batch-deadline-us", "2000",
    "--archive-checkpoint-every", "4",
    "--save-interval", "4",
    "--max-runtime-seconds", "14400",
    "--resume", "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
    "--allow-resume",
    "--reset-optimizer",
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--out", $out,
    "--seed", "2026072594"
)

& python @trainArgs 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
