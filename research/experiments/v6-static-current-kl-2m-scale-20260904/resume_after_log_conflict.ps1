$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
$parentExperiment = 'research/experiments/v6-static-current-kl-1m-scale-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'
$targetPhysicalHands = 2097152

$preflight = "$experiment/seed1_log_conflict_recovery_preflight.json"
python "$experiment/seed1_recovery_preflight.py" --out $preflight
if ($LASTEXITCODE -ne 0) { throw 'Seed1 recovery preflight failed' }

$seeds = @(
    @{ Name='seed1'; Seed=20263001; WorkerSeed=2026300100; DealStart=33300000; RunId='v6_nashpg_static_seed1_20260903'; Resume="$experiment/seed1/latest.pt" },
    @{ Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=34300000; RunId='v6_nashpg_static_seed2_20260903'; Resume="$parentExperiment/seed2/latest.pt" },
    @{ Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=35300000; RunId='v6_nashpg_static_seed3_20260903'; Resume="$parentExperiment/seed3/latest.pt" }
)

foreach ($seedInfo in $seeds) {
    $runDir = "$experiment/$($seedInfo.Name)"
    $out = "$runDir/latest.pt"
    if ($seedInfo.Name -ne 'seed1' -and (Test-Path -LiteralPath $out)) {
        throw "Refusing to overwrite unexpected checkpoint: $out"
    }
    $arguments = @(
        '-u', 'scripts/alpha_holdem/train_v5.py',
        '--device', 'cuda', '--workers', '12', '--hands-per-iter', '4096',
        '--total-hands', '99999999', '--total-environment-hands', [string]$targetPhysicalHands,
        '--starting-stack', '200', '--env-version', 'v6legacyv4obs', '--norm-layer', 'gn',
        '--lr', '0.0003', '--ppo-epochs', '2', '--ppo-target-kl', '0.01',
        '--policy-advantage-clip', '3', '--source-policy-kl-coef', '1',
        '--source-policy-kl-direction', 'current_to_reference',
        '--source-policy-reference-checkpoint', $standard10,
        '--separate-preflop-head', '--all-policy-heads-only-training',
        '--mini-batch-size', '16384', '--entropy-coef', '0.005', '--entropy-floor', '0.05',
        '--ppo-replay-buffer-iterations', '2', '--ppo-replay-ratio', '0.5',
        '--k-best', '5', '--pool-strategy', 'loss-kbest',
        '--initial-opponent-checkpoints', $standard10, $anchor2, $anchor3,
        '--hero-policy-mode', 'sample', '--self-play-fraction', '0.25',
        '--opponent-assignment', 'per-group', '--opponent-groups', '8',
        '--adaptive-opponent-league', '--adaptive-league-ema', '0.9',
        '--adaptive-league-temperature-bb', '2', '--adaptive-league-min-probability', '0.05',
        '--opponent-assignment-provenance-file', "$runDir/opponent_assignments.jsonl",
        '--resume-assignment-state-from-provenance', '--rollout-mode', 'single',
        '--rollout-envs-per-worker', '1', '--inference-min-batch-slots', '0',
        '--inference-batch-deadline-us', '700', '--worker-seed-base', [string]$seedInfo.WorkerSeed,
        '--fixed-training-deal-stream', '--fixed-training-deal-start-index', [string]$seedInfo.DealStart,
        '--critic-contract', 'critic_v2', '--h1-effective-stack-divisor', '200',
        '--h1-critic-init-seed', '2026071102', '--value-coef', '1',
        '--autonomous-critic-v2-continue', '--snapshot-every', '2', '--save-interval', '1',
        '--archive-checkpoint-every', '64', '--run-id', $seedInfo.RunId,
        '--run-dir', $runDir, '--out', $out, '--seed', [string]$seedInfo.Seed,
        '--max-runtime-seconds', '7200', '--resume', $seedInfo.Resume,
        '--allow-resume', '--no-reset-optimizer', '--preserve-resumed-optimizer-lr', '--validate-stream'
    )
    Write-Host "Continuing recovered static current-KL $($seedInfo.Name) to 2M"
    & python @arguments
    if ($LASTEXITCODE -ne 0) { throw "$($seedInfo.Name) continuation failed with exit code $LASTEXITCODE" }
    $physical = [int64](& python -c "import torch; print(int(torch.load(r'$out',map_location='cpu',weights_only=False)['environment_hand_accounting']['completed_hands']))")
    if ($physical -lt $targetPhysicalHands) {
        throw "$($seedInfo.Name) stopped safely below target at $physical physical hands"
    }
}

