$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$runId = "preflopv2_postflop_headcritic_mixedleague_1m_20260726"
$runDir = Join-Path "models" $runId
$out = Join-Path $runDir "latest.pt"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null

$source = "models/slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725/latest.pt"
$mimic = "models/slumbot_mimic_preflopv2_700k_20260725/best.pt"

$arguments = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--device", "cuda",
    "--workers", "28",
    "--hands-per-iter", "32768",
    "--total-hands", "1000000",
    "--reset-hand-counter",
    "--starting-stack", "200",
    "--env-version", "v55preflopv2v4obs",
    "--norm-layer", "gn",
    "--lr", "1e-6",
    "--ppo-epochs", "1",
    "--ppo-target-kl", "0.0",
    "--source-policy-kl-coef", "0.5",
    "--policy-postflop-only",
    "--separate-preflop-head",
    "--mini-batch-size", "2048",
    "--epsilon", "0.0",
    "--gamma", "0.999",
    "--gae-lambda", "1.0",
    "--delta1", "3.0",
    "--value-coef", "0.5",
    "--critic-head-only-gradient",
    "--entropy-coef", "0.0005",
    "--entropy-floor", "0.0",
    "--fixed-opponent-checkpoints",
        $source,
        $source,
        $mimic,
        $mimic,
    "--self-play-fraction", "0.0",
    "--opponent-assignment", "per-iteration",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "128",
    "--inference-batch-deadline-us", "2000",
    "--archive-checkpoint-every", "8",
    "--save-interval", "8",
    "--max-runtime-seconds", "1800",
    "--resume", $source,
    "--allow-resume",
    "--reset-optimizer",
    "--run-id", $runId,
    "--run-dir", $runDir,
    "--out", $out,
    "--seed", "2026072606"
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
