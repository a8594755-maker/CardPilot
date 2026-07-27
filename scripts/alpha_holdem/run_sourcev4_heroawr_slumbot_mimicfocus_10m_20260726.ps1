$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Start when the current main trainer and the short GAE comparison release GPU
# capacity.  Their CPU-only Slumbot screens may continue in parallel.
$trainingPatterns = @(
    'sourcev4_heroawr_mimic_league_rl10m_20260726',
    'sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726'
)
$deadline = (Get-Date).AddHours(2)
while ((Get-Date) -lt $deadline) {
    $active = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $command = $_.CommandLine
                if (
                    $_.Name -ne 'python.exe' -or
                    -not $command -or
                    $command -notmatch 'train_v5.py'
                ) {
                    return $false
                }
                foreach ($pattern in $trainingPatterns) {
                    if ($command -match $pattern) { return $true }
                }
                return $false
            }
    )
    if ($active.Count -eq 0) { break }
    Start-Sleep -Seconds 20
}
if ((Get-Date) -ge $deadline) {
    throw 'Timed out waiting for predecessor GPU trainers'
}

$gaeRecordPath = (
    'models\sourcev4_heroawr_league_criticv2_gae095_1p7m_20260726\' +
    'experiment_record.json'
)
$recordDeadline = (Get-Date).AddMinutes(30)
while (
    -not (Test-Path -LiteralPath $gaeRecordPath -PathType Leaf) -and
    (Get-Date) -lt $recordDeadline
) {
    Start-Sleep -Seconds 10
}
if (-not (Test-Path -LiteralPath $gaeRecordPath -PathType Leaf)) {
    throw 'GAE comparison record did not appear'
}
$gaeRecord = Get-Content -LiteralPath $gaeRecordPath -Raw | ConvertFrom-Json
$gaeLambda = if (
    [double]$gaeRecord.lambda_095_candidate_mean_bb_per_100 -gt
    [double]$gaeRecord.lambda_1_comparator_mean_bb_per_100
) {
    '0.95'
} else {
    '1.0'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\' +
        'selected.pt'
    )
).Path
$fixedOpponents = @(
    'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt',
    'models\sourcev4_slumbot_history500k_imitation_adapter256_kl01_mappingfix_20260726\best.pt',
    'models\sourcev4_slumbot_history500k_postflop_imitation_adapter256_kl01_mappingfix_20260726\best.pt',
    'models\sourcev4_slumbot_formal100k_preflop_imitation_head_lr3e4_kl01_mappingfix_20260726\best.pt',
    $source
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing mimic-focus training input: $path"
    }
}

$runDir = 'models\sourcev4_heroawr_slumbot_mimicfocus_10m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Mimic-focus output already exists: $runDir"
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
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1.0',
    '--autonomous-critic-v2-reset',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', $gaeLambda,
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
    '--run-id', 'sourcev4_heroawr_slumbot_mimicfocus_10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260806',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Slumbot mimic-focus 10M training failed'
}

$curveDir = Join-Path $runDir 'internal_curve'
New-Item -ItemType Directory -Path $curveDir | Out-Null
$candidatePaths = [ordered]@{ source = $source }
foreach ($iteration in @(50, 100, 200)) {
    $pattern = Join-Path (
        Join-Path $runDir 'checkpoints'
    ) ("checkpoint_iter{0:D6}_*.pt" -f $iteration)
    $matches = @(Get-ChildItem -Path $pattern -File)
    if ($matches.Count -ne 1) {
        throw "Expected one archived checkpoint for iteration $iteration"
    }
    $candidatePaths["iter$iteration"] = $matches[0].FullName
}
$candidatePaths['latest'] = Join-Path $runDir 'latest.pt'

$curve = foreach ($entry in $candidatePaths.GetEnumerator()) {
    $json = Join-Path $curveDir "$($entry.Key).json"
    $probeOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 1000 `
        --opponents aggressive call-station random `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260777 `
        --policy-mode greedy `
        --out-json $json `
        --out-md (Join-Path $curveDir "$($entry.Key).md")
    $probeOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Mimic-focus internal probe failed: $($entry.Key)"
    }
    $probe = Get-Content -LiteralPath $json -Raw | ConvertFrom-Json
    $mimicJson = Join-Path $curveDir "$($entry.Key)_mimic.json"
    $mimicOutput = & python -X utf8 -u `
        scripts/alpha_holdem/v5_internal_strength_probe.py `
        --checkpoint $entry.Value `
        --hands 2000 `
        --checkpoint-opponent ($fixedOpponents[0]) `
        --checkpoint-opponent-only `
        --checkpoint-opponent-policy-mode greedy `
        --max-pool-snapshots 0 `
        --device cuda `
        --starting-stack 200 `
        --seed 20260807 `
        --policy-mode greedy `
        --out-json $mimicJson `
        --out-md (Join-Path $curveDir "$($entry.Key)_mimic.md")
    $mimicOutput | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Mimic-focus proxy probe failed: $($entry.Key)"
    }
    $mimicProbe = Get-Content -LiteralPath $mimicJson -Raw | ConvertFrom-Json
    [pscustomobject]@{
        name = $entry.Key
        checkpoint = $entry.Value
        mean_bb_per_100 = [double](
            ($probe.results | Measure-Object -Property bb100 -Average).Average
        )
        mimic_proxy_bb_per_100 = [double](
            ($mimicProbe.results | Measure-Object -Property bb100 -Average).Average
        )
        total_hands = [int64]$probe.checkpoint.total_hands
        results = $probe.results
        mimic_results = $mimicProbe.results
    }
}
$best = $curve |
    Where-Object name -ne 'source' |
    Sort-Object mimic_proxy_bb_per_100 -Descending |
    Select-Object -First 1
$selected = Join-Path $runDir 'selected.pt'
Copy-Item -LiteralPath $best.checkpoint -Destination $selected
$selectedSha = (
    Get-FileHash -LiteralPath $selected -Algorithm SHA256
).Hash.ToLowerInvariant()
$newHands = [int64]$best.total_hands - 262472

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'PPO against high-coverage learned Slumbot imitation opponents provides ' +
        'a more externally relevant gradient than the generic five-policy league.'
    )
    material_change = (
        'Fresh critic-v2 postflop adapter trained against four learned Slumbot ' +
        'imitation checkpoints plus the source policy; GAE lambda selected by ' +
        'the completed same-start comparison.'
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
    gae_lambda = [double]$gaeLambda
    new_training_hands = $newHands
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = 500000
    curve = $curve
    selected_checkpoint = (Resolve-Path -LiteralPath $selected).Path
    selected_checkpoint_sha256 = $selectedSha
    external_gate = 'One selected 10M-lineage milestone always receives fresh5k.'
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_heroawr_slumbot_mimicfocus_10m_' +
    'pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $selected).Path `
    -Tag 'sourcev4_heroawr_slumbot_mimicfocus_10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Slumbot mimic-focus 10M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_slumbot_mimicfocus_10m' `
    -QuickDir $externalDir `
    -SourcePolicy $selected `
    -OutputStem 'sourcev4_heroawr_slumbot_mimicfocus_10m' `
    -TrainingMethod 'critic-v2 PPO against a five-member Slumbot-mimic league' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
