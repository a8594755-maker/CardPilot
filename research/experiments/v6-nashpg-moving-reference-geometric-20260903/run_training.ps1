$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-nashpg-moving-reference-geometric-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'

foreach ($required in @($standard10, $anchor2, $anchor3)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing immutable input: $required"
    }
}

python -m pytest -q `
    scripts/alpha_holdem/test_source_policy_moving_reference.py `
    scripts/alpha_holdem/test_source_policy_kl_temperature.py `
    scripts/alpha_holdem/test_ppo_gradient_update_equivalence.py
if ($LASTEXITCODE -ne 0) { throw 'Moving-reference preflight tests failed' }

$seeds = @(
    @{ Name = 'seed1'; Seed = 20263001; WorkerSeed = 2026300100; DealStart = 30000000 },
    @{ Name = 'seed2'; Seed = 20263002; WorkerSeed = 2026300200; DealStart = 31000000 },
    @{ Name = 'seed3'; Seed = 20263003; WorkerSeed = 2026300300; DealStart = 32000000 }
)

foreach ($seedInfo in $seeds) {
    foreach ($arm in @('static', 'moving')) {
        $runDir = "$experiment/$arm`_$($seedInfo.Name)"
        $out = "$runDir/latest.pt"
        $assignment = "$runDir/opponent_assignments.jsonl"
        if (Test-Path -LiteralPath $out) {
            throw "Refusing to overwrite existing run: $out"
        }
        $runId = "v6_nashpg_$arm`_$($seedInfo.Name)_20260903"
        $arguments = @(
            '-u', 'scripts/alpha_holdem/train_v5.py',
            '--device', 'cuda',
            '--workers', '12',
            '--hands-per-iter', '4096',
            '--total-hands', '99999999',
            '--total-environment-hands', '65536',
            '--starting-stack', '200',
            '--env-version', 'v6legacyv4obs',
            '--v6-rebind-legacy-weights',
            '--norm-layer', 'gn',
            '--lr', '0.0003',
            '--ppo-epochs', '2',
            '--ppo-target-kl', '0.01',
            '--policy-advantage-clip', '3',
            '--source-policy-kl-coef', '1',
            '--source-policy-kl-direction', 'current_to_reference',
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
            '--rollout-mode', 'single',
            '--rollout-envs-per-worker', '1',
            '--inference-min-batch-slots', '0',
            '--inference-batch-deadline-us', '700',
            '--worker-seed-base', [string]$seedInfo.WorkerSeed,
            '--fixed-training-deal-stream',
            '--fixed-training-deal-start-index', [string]$seedInfo.DealStart,
            '--critic-contract', 'critic_v2',
            '--h1-effective-stack-divisor', '200',
            '--h1-critic-init-seed', '2026071102',
            '--value-coef', '1',
            '--autonomous-critic-v2-continue',
            '--snapshot-every', '2',
            '--save-interval', '1',
            '--archive-checkpoint-every', '4',
            '--run-id', $runId,
            '--run-dir', $runDir,
            '--out', $out,
            '--seed', [string]$seedInfo.Seed,
            '--max-runtime-seconds', '3600',
            '--resume', $standard10,
            '--allow-resume',
            '--reset-hand-counter',
            '--reset-optimizer',
            '--validate-stream'
        )
        if ($arm -eq 'moving') {
            $arguments += @('--source-policy-reference-refresh-updates', '1')
        }
        Write-Host "Starting $arm $($seedInfo.Name)"
        & python @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$arm $($seedInfo.Name) failed with exit code $LASTEXITCODE"
        }
    }
}
