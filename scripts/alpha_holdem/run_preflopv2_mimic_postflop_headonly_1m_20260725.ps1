$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "slumbot_br_preflopv2_mimic_postflop_headonly_1m_20260725"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$arguments = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--device", "cuda",
    "--workers", "20",
    "--hands-per-iter", "32768",
    "--total-hands", "1000000",
    "--reset-hand-counter",
    "--starting-stack", "200",
    "--env-version", "v55preflopv2v4obs",
    "--norm-layer", "gn",
    "--lr", "1e-4",
    "--ppo-epochs", "2",
    "--ppo-target-kl", "0.01",
    "--source-policy-kl-coef", "0.1",
    "--policy-postflop-only",
    "--head-only-training",
    "--separate-preflop-head",
    "--mini-batch-size", "2048",
    "--epsilon", "0.0",
    "--gamma", "0.999",
    "--gae-lambda", "1.0",
    "--delta1", "3.0",
    "--value-coef", "0.25",
    "--entropy-coef", "0.001",
    "--entropy-floor", "0.0",
    "--fixed-opponent-checkpoint",
        "models/slumbot_mimic_preflopv2_700k_20260725/best.pt",
    "--self-play-fraction", "0.0",
    "--opponent-assignment", "per-iteration",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "96",
    "--inference-batch-deadline-us", "2000",
    "--archive-checkpoint-every", "4",
    "--save-interval", "4",
    "--max-runtime-seconds", "1800",
    "--resume",
        "models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt",
    "--allow-resume",
    "--reset-optimizer",
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--out", $out,
    "--seed", "202607253"
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
