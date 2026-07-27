$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$priorRun = 'sourcev4_postflop_adapter128_rl_scale10m_20260726'
$deadline = (Get-Date).AddHours(8)
while ((Get-Date) -lt $deadline) {
    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -eq 'python.exe' -and
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match $priorRun
            }
    )
    if ($trainer.Count -eq 0) { break }
    Start-Sleep -Seconds 30
}
if ((Get-Date) -ge $deadline) {
    throw 'Timed out waiting for the conservative scale-10M trainer'
}

$runDir = 'models\sourcev4_heroawr_mimic_league_rl10m_20260726'
$source = 'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\selected.pt'
$continuationCheckpoint = Join-Path $runDir 'latest.pt'
$isContinuation = Test-Path -LiteralPath $continuationCheckpoint -PathType Leaf
if ((Test-Path -LiteralPath $runDir) -and -not $isContinuation) {
    throw "Training output exists without a resumable latest checkpoint: $runDir"
}
$resumeCheckpoint = if ($isContinuation) {
    $continuationCheckpoint
} else {
    $source
}
$fixedOpponents = @(
    $source,
    'models\slumbot_br_preflopv2_pokerskill_direct_distill_v2_20260725\latest.pt',
    'models\sourcev4_slumbot_formal100k_postflop_awr_adapter256_mappingfix_20260726\epoch_1.pt',
    'models\sourcev4_slumbot_formal100k_bb_postflop_awr_adapter256_20260726\epoch_3.pt',
    'models\sourcev4_postflop_adapter128_rl_scale10m_20260726\latest.pt'
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing training input: $path"
    }
}

$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', '10262472',
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
    '--run-id', 'sourcev4_heroawr_mimic_league_rl10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260766',
    '--max-runtime-seconds', '21600',
    '--resume', $resumeCheckpoint,
    '--allow-resume'
)
if (-not $isContinuation) {
    $args += '--reset-optimizer'
} else {
    $args += '--no-reset-optimizer'
}
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Hero-AWR mimic-league RL10M training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$externalDir = 'models\bench_sourcev4_heroawr_mimic_league_rl10m_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag 'sourcev4_heroawr_mimic_league_rl10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Hero-AWR mimic-league fresh5k failed'
}

$finalHandsText = & python -X utf8 -c `
    "import torch; c=torch.load(r'$candidate',map_location='cpu',weights_only=False); print(int(c['total_hands']))"
if ($LASTEXITCODE -ne 0) {
    throw 'Could not read final mimic-league hand count'
}
$newHands = [int64]$finalHandsText - 262472
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_mimic_league_rl10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_mimic_league_rl10m' `
    -TrainingMethod 'five-member fixed pure-policy opponent-league PPO from hero-AWR weights' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
