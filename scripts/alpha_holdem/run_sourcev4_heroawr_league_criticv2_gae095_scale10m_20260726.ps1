$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726\' +
        'latest.pt'
    )
).Path
$sourceHands = 5022978
$runDir = (
    'models\sourcev4_heroawr_league_criticv2_gae095_scale10m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "GAE-0.95 scale output already exists: $runDir"
}
$fixedOpponents = @(
    'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\selected.pt',
    'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt',
    'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt',
    'models\sourcev4_slumbot_formal100k_bb_postflop_awr_adapter256_20260726\epoch_3.pt',
    'models\sourcev4_postflop_adapter128_rl_scale10m_20260726\latest.pt'
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing GAE-0.95 scale input: $path"
    }
}

$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '10',
    '--hands-per-iter', '32768',
    '--total-hands', '10000000',
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.00003',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.01',
    '--source-policy-kl-coef', '0.25',
    '--policy-postflop-only',
    '--separate-preflop-head',
    '--postflop-adapter-hidden', '256',
    '--adapter-only-training',
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1.0',
    '--autonomous-critic-v2-reset',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', '0.95',
    '--delta1', '3',
    '--entropy-coef', '0.002',
    '--entropy-floor', '0',
    '--k-best', '3',
    '--pool-strategy', 'latest',
    '--self-play-fraction', '0',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '5',
    '--fixed-opponent-checkpoints'
) + $fixedOpponents + @(
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '25',
    '--save-interval', '5',
    '--archive-checkpoint-every', '25',
    '--run-id', 'sourcev4_heroawr_league_criticv2_gae095_scale10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260810',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'GAE-0.95 scale-10M training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$probeDir = Join-Path $runDir 'internal_endpoint'
New-Item -ItemType Directory -Path $probeDir | Out-Null
$probeJson = Join-Path $probeDir 'candidate.json'
$probeOutput = & python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260777 `
    --policy-mode greedy `
    --out-json $probeJson `
    --out-md (Join-Path $probeDir 'candidate.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'GAE-0.95 scale endpoint probe failed'
}
$probe = Get-Content -LiteralPath $probeJson -Raw | ConvertFrom-Json
$candidateHands = [int64]$probe.checkpoint.total_hands
$newHands = $candidateHands - $sourceHands

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The same-start GAE-lambda-0.95 advantage persists when extended from ' +
        '5.02M to the 10M total-hand milestone.'
    )
    material_change = (
        'Continue the retained critic-v2 GAE-0.95 optimizer/checkpoint to 10M; ' +
        'the inferior lambda-1 scale run was stopped at 6.565M.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = $newHands
    inherited_lineage_training_hands = 6206948
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    stable_internal_mean_bb_per_100 = [double](
        ($probe.results | Measure-Object -Property bb100 -Average).Average
    )
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_heroawr_league_criticv2_gae095_scale10m_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_heroawr_league_criticv2_gae095_scale10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'GAE-0.95 scale-10M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_league_criticv2_gae095_scale10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_league_criticv2_gae095_scale10m' `
    -TrainingMethod 'critic-v2 GAE-lambda-0.95 fixed-policy league PPO to 10M' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 6206948 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
