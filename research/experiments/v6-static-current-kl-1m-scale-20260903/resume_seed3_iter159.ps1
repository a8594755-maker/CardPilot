$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-1m-scale-20260903'
$runDir = "$experiment/seed3"
$checkpoint = "$runDir/latest.pt"
$assignment = "$runDir/opponent_assignments.jsonl"
$preflightPath = "$experiment/seed3_resume_preflight_iter159.json"
$standard10 = 'models/baseline/standard10/latest.pt'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'

$preflight = Get-Content -Raw -LiteralPath $preflightPath | ConvertFrom-Json
if ($preflight.status -ne 'PASS') {
    throw "Resume preflight is not PASS: $preflightPath"
}
$actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $checkpoint).Hash.ToLower()
if ($actualSha -ne $preflight.checkpoint.sha256) {
    throw 'Interrupted seed3 checkpoint SHA256 mismatch'
}
if ([int64]$preflight.fixed_deal_recovery.deal_start_index -ne 32700000) {
    throw 'Unexpected recovery deal start'
}

$arguments = @(
    '-u', 'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '12',
    '--hands-per-iter', '4096',
    '--total-hands', '99999999',
    '--total-environment-hands', '1048576',
    '--starting-stack', '200',
    '--env-version', 'v6legacyv4obs',
    '--norm-layer', 'gn',
    '--lr', '0.0003',
    '--ppo-epochs', '2',
    '--ppo-target-kl', '0.01',
    '--policy-advantage-clip', '3',
    '--source-policy-kl-coef', '1',
    '--source-policy-kl-direction', 'current_to_reference',
    '--source-policy-reference-checkpoint', $standard10,
    '--separate-preflop-head',
    '--all-policy-heads-only-training',
    '--mini-batch-size', '16384',
    '--entropy-coef', '0.005',
    '--entropy-floor', '0.05',
    '--ppo-replay-buffer-iterations', '2',
    '--ppo-replay-ratio', '0.5',
    '--k-best', '5',
    '--pool-strategy', 'loss-kbest',
    '--initial-opponent-checkpoints', $standard10, $anchor2, $anchor3,
    '--hero-policy-mode', 'sample',
    '--self-play-fraction', '0.25',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '8',
    '--adaptive-opponent-league',
    '--adaptive-league-ema', '0.9',
    '--adaptive-league-temperature-bb', '2',
    '--adaptive-league-min-probability', '0.05',
    '--opponent-assignment-provenance-file', $assignment,
    '--resume-assignment-state-from-provenance',
    '--rollout-mode', 'single',
    '--rollout-envs-per-worker', '1',
    '--inference-min-batch-slots', '0',
    '--inference-batch-deadline-us', '700',
    '--worker-seed-base', '2026300300',
    '--fixed-training-deal-stream',
    '--fixed-training-deal-start-index', '32700000',
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--h1-critic-init-seed', '2026071102',
    '--value-coef', '1',
    '--autonomous-critic-v2-continue',
    '--snapshot-every', '2',
    '--save-interval', '1',
    '--archive-checkpoint-every', '64',
    '--run-id', 'v6_nashpg_static_seed3_20260903',
    '--run-dir', $runDir,
    '--out', $checkpoint,
    '--seed', '20263003',
    '--max-runtime-seconds', '7200',
    '--resume', $checkpoint,
    '--allow-resume',
    '--no-reset-optimizer',
    '--preserve-resumed-optimizer-lr',
    '--validate-stream'
)

& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Seed3 second recovery continuation failed with exit code $LASTEXITCODE"
}
