$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "stage4_pure_selfplay_10m_20260726"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$arguments = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--device", "cuda",
    "--workers", "28",
    "--hands-per-iter", "32768",
    "--total-hands", "10000000",
    "--reset-hand-counter",
    "--starting-stack", "200",
    "--env-version", "v55v4obs",
    "--norm-layer", "gn",
    "--lr", "3e-6",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0.0",
    "--source-policy-kl-coef", "0.05",
    "--mini-batch-size", "2048",
    "--epsilon", "0.0",
    "--gamma", "0.999",
    "--gae-lambda", "1.0",
    "--delta1", "3.0",
    "--value-coef", "0.5",
    "--entropy-coef", "0.001",
    "--entropy-floor", "0.0",
    "--self-play-fraction", "1.0",
    "--pool-strategy", "loss-kbest",
    "--k-best", "5",
    "--opponent-assignment", "per-worker",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "128",
    "--inference-batch-deadline-us", "2000",
    "--mirror-self-play-deals",
    "--archive-checkpoint-every", "32",
    "--save-interval", "8",
    "--max-runtime-seconds", "10800",
    "--resume",
        "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
    "--allow-resume",
    "--reset-optimizer",
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--out", $out,
    "--seed", "2026072601"
)

$process = Start-Process -FilePath python `
    -ArgumentList $arguments `
    -WorkingDirectory $repo `
    -RedirectStandardOutput "$repo/$runDir/train.stdout.log" `
    -RedirectStandardError "$repo/$runDir/train.stderr.log" `
    -WindowStyle Hidden `
    -Wait `
    -PassThru
exit $process.ExitCode
