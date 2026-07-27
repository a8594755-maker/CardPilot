$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_heroawr_league_iter50_criticv2_' +
        '3p315m_selected_20260726.pt'
    )
).Path
$runDir = 'models\sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Training output already exists: $runDir"
}
$fixedOpponents = @(
    'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\selected.pt',
    'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt',
    'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt',
    'models\sourcev4_slumbot_formal100k_bb_postflop_awr_adapter256_20260726\epoch_3.pt',
    'models\sourcev4_postflop_adapter128_rl_scale10m_20260726\latest.pt'
)

$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '10',
    '--hands-per-iter', '32768',
    '--total-hands', '5000000',
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
    '--run-id', 'sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260803',
    '--max-runtime-seconds', '7200',
    '--resume', $source,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 GAE-0.95 comparison training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$probeDir = Join-Path $runDir 'internal_curve'
New-Item -ItemType Directory -Path $probeDir | Out-Null
$candidateJson = Join-Path $probeDir 'candidate.json'
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
    --out-json $candidateJson `
    --out-md (Join-Path $probeDir 'candidate.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 GAE-0.95 internal probe failed'
}

$lambdaOneCheckpoint = $null
$deadline = (Get-Date).AddHours(1)
while ((Get-Date) -lt $deadline) {
    $matches = @(
        Get-ChildItem -Path (
            'models\sourcev4_heroawr_league_criticv2_scale10m_20260726\' +
            'checkpoints\checkpoint_iter000150_*.pt'
        ) -File -ErrorAction SilentlyContinue
    )
    if ($matches.Count -eq 1) {
        $lambdaOneCheckpoint = $matches[0]
        break
    }
    Start-Sleep -Seconds 20
}
if ($null -eq $lambdaOneCheckpoint) {
    throw 'Comparable lambda-1.0 iteration-150 checkpoint did not appear'
}
$lambdaOneJson = Join-Path $probeDir 'lambda1_iter150.json'
$probeOutput = & python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $lambdaOneCheckpoint.FullName `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260777 `
    --policy-mode greedy `
    --out-json $lambdaOneJson `
    --out-md (Join-Path $probeDir 'lambda1_iter150.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 lambda-1.0 comparison probe failed'
}

$initial = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_league_iter50_criticv2_1p64m_20260726\' +
    'internal_curve\candidate.json'
) -Raw | ConvertFrom-Json
$candidateProbe = Get-Content -LiteralPath $candidateJson -Raw | ConvertFrom-Json
$lambdaOneProbe = Get-Content -LiteralPath $lambdaOneJson -Raw | ConvertFrom-Json
$initialMean = [double](
    ($initial.results | Measure-Object -Property bb100 -Average).Average
)
$candidateMean = [double](
    ($candidateProbe.results | Measure-Object -Property bb100 -Average).Average
)
$lambdaOneMean = [double](
    ($lambdaOneProbe.results | Measure-Object -Property bb100 -Average).Average
)
$runExternal = (
    $candidateMean -ge ($initialMean - 10.0) -and
    $candidateMean -ge ($lambdaOneMean + 20.0)
)
$candidateHands = [int64]$candidateProbe.checkpoint.total_hands
$newHands = $candidateHands - 3315295
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'With a normalized learned critic, GAE lambda 0.95 reduces actor-target ' +
        'variance and improves stable generalization versus lambda 1.0.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    material_change = 'GAE lambda 1.0 to 0.95; all other training settings fixed.'
    new_training_hands = $newHands
    inherited_lineage_training_hands = 4499265
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    stable_internal_seed = 20260777
    initial_critic_v2_mean_bb_per_100 = $initialMean
    lambda_1_comparator_checkpoint = $lambdaOneCheckpoint.FullName
    lambda_1_comparator_mean_bb_per_100 = $lambdaOneMean
    lambda_095_candidate_mean_bb_per_100 = $candidateMean
    external_gate = (
        'candidate >= initial critic-v2-10 and candidate >= lambda-1 comparator+20'
    )
    run_fresh5k = $runExternal
    decision = if ($runExternal) { 'RETAIN_AND_SCREEN' } else { 'REJECT' }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
if (-not $runExternal) { exit 0 }

$externalDir = (
    'models\bench_sourcev4_heroawr_league_criticv2_gae095_1p7m_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_heroawr_league_criticv2_gae095_1p7m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 GAE-0.95 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_league_criticv2_gae095_1p7m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_league_criticv2_gae095_1p7m' `
    -TrainingMethod 'normalized critic-v2 GAE-lambda-0.95 fixed-policy league PPO' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 4499265 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
