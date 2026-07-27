$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "slumbot_br_pfv2_postflop_adapt_1m_20260725"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
$stdout = Join-Path $runDir "train.stdout.log"
$stderr = Join-Path $runDir "train.stderr.log"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$trainArgs = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--resume", "models/slumbot_br_pfv2_pokerskill_direct_distill_20260725/latest.pt",
    "--allow-resume",
    "--out", $out,
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--device", "cuda",
    "--workers", "20",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "128",
    "--inference-batch-deadline-us", "2000",
    "--env-version", "v55pfv2v4obs",
    "--norm-layer", "gn",
    "--total-hands", "1000000",
    "--hands-per-iter", "32768",
    "--lr", "0.000001",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0.01",
    "--mini-batch-size", "2048",
    "--gamma", "0.999",
    "--gae-lambda", "1",
    "--delta1", "3",
    "--value-coef", "0.25",
    "--entropy-coef", "0.001",
    "--entropy-floor", "0",
    "--source-policy-kl-coef", "0.10",
    "--policy-postflop-only",
    "--hero-preflop-strategy", "model",
    "--preflop-teacher-coef", "0",
    "--separate-preflop-head",
    "--hero-policy-mode", "sample",
    "--epsilon", "0",
    "--self-play-fraction", "0",
    "--fixed-opponent-checkpoints",
        "models/slumbot_mimic_pfv2_700k_20260725/best.pt",
    "--opponent-assignment", "per-iteration",
    "--pool-strategy", "loss-kbest",
    "--k-best", "1",
    "--reset-hand-counter",
    "--reset-optimizer",
    "--overwrite",
    "--save-interval", "4",
    "--archive-checkpoint-every", "4",
    "--max-runtime-seconds", "7200",
    "--seed", "2026072598"
)

& python @trainArgs 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
