$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $repo

$stdout = "models/preflop_teacher_v14b_launcher.stdout.log"
$stderr = "models/preflop_teacher_v14b_launcher.stderr.log"

$arguments = @(
    "-X", "utf8", "-u",
    "scripts/alpha_holdem/train_v5.py",
    "--resume", "models/slumbot_br_ensemble4_stage4fast_1m_20260725/latest.pt",
    "--allow-resume",
    "--out", "models/slumbot_br_preflop_teacher_v14b_262k_20260725/latest.pt",
    "--run-id", "slumbot_br_preflop_teacher_v14b_262k_20260725",
    "--device", "cuda",
    "--workers", "20",
    "--rollout-mode", "multi",
    "--rollout-envs-per-worker", "16",
    "--inference-min-batch-slots", "160",
    "--inference-batch-deadline-us", "2000",
    "--env-version", "v55v4obs",
    "--norm-layer", "gn",
    "--total-hands", "262144",
    "--hands-per-iter", "32768",
    "--lr", "0.000003",
    "--ppo-epochs", "2",
    "--ppo-target-kl", "0.01",
    "--mini-batch-size", "1024",
    "--gamma", "0.999",
    "--gae-lambda", "1",
    "--delta1", "3",
    "--value-coef", "0.5",
    "--entropy-coef", "0",
    "--entropy-floor", "0",
    "--source-policy-kl-coef", "0.5",
    "--policy-postflop-only",
    "--hero-preflop-strategy", "heuristic-v4",
    "--preflop-teacher-coef", "1.0",
    "--separate-preflop-head",
    "--preflop-head-lr", "0.00003",
    "--hero-policy-mode", "sample",
    "--epsilon", "0",
    "--self-play-fraction", "0",
    "--fixed-opponent-checkpoints",
    "models/slumbot_imitation_all413_plain_seed61_20260725/best.pt",
    "models/slumbot_imitation_all413_risk05_seed62_20260725/best.pt",
    "models/slumbot_imitation_recent15_seed46_300k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk075_seed47_300k_20260725/best.pt",
    "models/slumbot_imitation_subset_seed33_350k_20260725/best.pt",
    "models/slumbot_imitation_recent15_risk1_seed48_holdout_300k_20260725/best.pt",
    "--opponent-assignment", "per-iteration",
    "--pool-strategy", "loss-kbest",
    "--k-best", "5",
    "--reset-hand-counter",
    "--reset-optimizer",
    "--overwrite",
    "--save-interval", "1",
    "--archive-checkpoint-every", "2"
)

$process = Start-Process -FilePath python `
    -ArgumentList $arguments `
    -WorkingDirectory $repo `
    -RedirectStandardOutput "$repo/$stdout" `
    -RedirectStandardError "$repo/$stderr" `
    -WindowStyle Hidden `
    -PassThru

$process.WaitForExit()
$process.Refresh()
if ($null -eq $process.ExitCode -or $process.ExitCode -ne 0) {
    throw "v14b trainer failed: pid=$($process.Id) exit_code=$($process.ExitCode)"
}
