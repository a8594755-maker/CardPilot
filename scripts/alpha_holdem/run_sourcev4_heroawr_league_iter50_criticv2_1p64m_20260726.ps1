$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = @(
    Get-ChildItem -Path (
        'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
        'checkpoints\checkpoint_iter000050_*.pt'
    ) -File
)
if ($source.Count -ne 1) {
    throw "Expected one iteration-50 source checkpoint, found $($source.Count)"
}
$runDir = (
    'models\sourcev4_heroawr_league_iter50_criticv2_1p64m_20260726'
)
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
foreach ($path in $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing training opponent: $path"
    }
}

$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '10',
    '--hands-per-iter', '32768',
    '--total-hands', '3284681',
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
    '--gae-lambda', '1.0',
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
    '--run-id', 'sourcev4_heroawr_league_iter50_criticv2_1p64m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260788',
    '--max-runtime-seconds', '7200',
    '--resume', $source[0].FullName,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 comparison training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$probeDir = Join-Path $runDir 'internal_curve'
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
    throw 'Critic-v2 internal probe failed'
}

$sourceProbe = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_1p64m\source_hero_awr.json'
) -Raw | ConvertFrom-Json
$criticV1Probe = Get-Content -LiteralPath (
    'models\sourcev4_heroawr_mimic_league_rl10m_20260726\' +
    'internal_curve_3p28m\summary.json'
) -Raw | ConvertFrom-Json
$candidateProbe = Get-Content -LiteralPath $probeJson -Raw | ConvertFrom-Json
$sourceMean = [double](
    ($sourceProbe.results | Measure-Object -Property bb100 -Average).Average
)
$criticV1Mean = [double]$criticV1Probe.candidate_mean_bb_per_100
$candidateMean = [double](
    ($candidateProbe.results | Measure-Object -Property bb100 -Average).Average
)
$runExternal = (
    $candidateMean -ge ($sourceMean - 10.0) -and
    $candidateMean -ge ($criticV1Mean + 20.0)
)
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A deeper critic with 200bb-normalized targets reduces the late-policy ' +
        'drift seen with the single-layer raw-BB critic.'
    )
    material_change = (
        'From the exact iteration-50 actor: critic_v1 to freshly initialized ' +
        'critic_v2, normalized returns, fresh Adam; all actor/league settings fixed.'
    )
    source_checkpoint = $source[0].FullName
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source[0].FullName -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = 1642988
    inherited_lineage_training_hands = 2825663
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    stable_internal_seed = 20260777
    stable_internal_hands_per_opponent = 1000
    source_mean_bb_per_100 = $sourceMean
    critic_v1_same_endpoint_mean_bb_per_100 = $criticV1Mean
    critic_v2_candidate_mean_bb_per_100 = $candidateMean
    external_gate = (
        'candidate >= source-10 and candidate >= critic_v1 same endpoint+20'
    )
    run_fresh5k = $runExternal
    decision = if ($runExternal) { 'RETAIN_AND_SCREEN' } else { 'REJECT' }
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
if (-not $runExternal) { exit 0 }

$externalDir = (
    'models\bench_sourcev4_heroawr_league_iter50_criticv2_1p64m_' +
    'pure_fresh5k_20260726'
)
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag (
        'sourcev4_heroawr_league_iter50_criticv2_1p64m_' +
        'pure_fresh5k_20260726'
    ) `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Critic-v2 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_league_iter50_criticv2_1p64m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_league_iter50_criticv2_1p64m' `
    -TrainingMethod (
        'normalized deeper critic-v2 fixed pure-policy league PPO from ' +
        'iteration-50 hero-AWR league actor'
    ) `
    -NewTrainingHands 1642988 `
    -InheritedLineageTrainingHands 2825663 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
