$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "slumbot_br_pfv2_pokerskill_teacher_262k_20260725"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
$stdout = Join-Path $runDir "train.stdout.log"
$stderr = Join-Path $runDir "train.stderr.log"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$trainArgs = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--resume", "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
    "--allow-resume",
    "--out", $out,
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--device", "cuda",
    "--workers", "20",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "160",
    "--inference-batch-deadline-us", "2000",
    "--env-version", "v55pfv2v4obs",
    "--norm-layer", "gn",
    "--total-hands", "262144",
    "--hands-per-iter", "32768",
    "--lr", "0",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0",
    "--mini-batch-size", "1024",
    "--gamma", "0.999",
    "--gae-lambda", "1",
    "--delta1", "3",
    "--value-coef", "0",
    "--entropy-coef", "0",
    "--entropy-floor", "0",
    "--source-policy-kl-coef", "0",
    "--policy-postflop-only",
    "--hero-preflop-strategy", "pokerskill-v1",
    "--preflop-teacher-coef", "1.0",
    "--separate-preflop-head",
    "--preflop-head-lr", "0.00003",
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
    "--save-interval", "1",
    "--archive-checkpoint-every", "2",
    "--max-runtime-seconds", "7200",
    "--seed", "2026072596"
)

& python @trainArgs 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
