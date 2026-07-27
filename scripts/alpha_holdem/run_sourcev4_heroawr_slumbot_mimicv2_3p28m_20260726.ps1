$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$mimicRecordPath = (
    'models\sourcev4_slumbot_history500k_postflop_imitation_' +
    'fullnet_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(2)
while (
    -not (Test-Path -LiteralPath $mimicRecordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $mimicRecordPath -PathType Leaf)) {
    throw 'Timed out waiting for full-network Slumbot imitation'
}
$mimicRecord = Get-Content -LiteralPath $mimicRecordPath -Raw |
    ConvertFrom-Json
if ($mimicRecord.decision -ne 'RETAIN_AS_TRAINING_OPPONENT') {
    exit 0
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
        'selected.pt'
    )
).Path
$newMimicDir = (
    'models\sourcev4_slumbot_history500k_postflop_imitation_' +
    'fullnet_20260726'
)
$fixedOpponents = @(
    (Join-Path $newMimicDir 'best.pt'),
    (Join-Path $newMimicDir 'epoch_1.pt'),
    'models\sourcev4_slumbot_history500k_imitation_adapter256_kl01_mappingfix_20260726\best.pt',
    'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt',
    $source
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing mimic-v2 input: $path"
    }
}

$runDir = 'models\sourcev4_heroawr_slumbot_mimicv2_3p28m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Mimic-v2 output already exists: $runDir"
}
$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', '3540152',
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
    '--run-id', 'sourcev4_heroawr_slumbot_mimicv2_3p28m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260811',
    '--max-runtime-seconds', '10800',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Slumbot mimic-v2 3.28M training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$probeDir = Join-Path $runDir 'internal_endpoint'
New-Item -ItemType Directory -Path $probeDir | Out-Null
$genericJson = Join-Path $probeDir 'candidate.json'
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
    --out-json $genericJson `
    --out-md (Join-Path $probeDir 'candidate.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 generic endpoint probe failed'
}
$generic = Get-Content -LiteralPath $genericJson -Raw | ConvertFrom-Json

$mimicJson = Join-Path $probeDir 'candidate_mimic.json'
$probeOutput = & python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 2000 `
    --checkpoint-opponent ($fixedOpponents[0]) `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode sample `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260807 `
    --policy-mode greedy `
    --out-json $mimicJson `
    --out-md (Join-Path $probeDir 'candidate_mimic.md')
$probeOutput | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 local-opponent endpoint probe failed'
}
$mimic = Get-Content -LiteralPath $mimicJson -Raw | ConvertFrom-Json
$candidateHands = [int64]$generic.checkpoint.total_hands
$newHands = $candidateHands - 262472

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A higher-accuracy full-network Slumbot imitation league produces a ' +
        'more transferable postflop best-response gradient.'
    )
    material_change = (
        'Fresh critic-v2 GAE-0.95 postflop adapter trained for 3.28M hands ' +
        'against a league emphasizing the retained full-network mimic.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    fixed_opponents = @(
        foreach ($path in $fixedOpponents) {
            [ordered]@{
                path = (Resolve-Path -LiteralPath $path).Path
                sha256 = (
                    Get-FileHash -LiteralPath $path -Algorithm SHA256
                ).Hash.ToLowerInvariant()
            }
        }
    )
    new_training_hands = $newHands
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    stable_internal_mean_bb_per_100 = [double](
        ($generic.results | Measure-Object -Property bb100 -Average).Average
    )
    mimic_v2_mean_bb_per_100 = [double](
        ($mimic.results | Measure-Object -Property bb100 -Average).Average
    )
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_heroawr_slumbot_mimicv2_3p28m_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_heroawr_slumbot_mimicv2_3p28m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Slumbot mimic-v2 3.28M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_slumbot_mimicv2_3p28m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_slumbot_mimicv2_3p28m' `
    -TrainingMethod 'critic-v2 GAE-0.95 PPO against full-network Slumbot mimic-v2 league' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
