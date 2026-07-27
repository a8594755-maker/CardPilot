param(
    [int]$WaitForPid = 0
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runId = 'sourcev4_scaledteacher_position_actor_value_isolated_diverse10m_20260727'
$runDir = Join-Path 'models' $runId
$recordPath = Join-Path $runDir 'experiment_record.json'
$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_slumbot_history_allstreet_' +
        'imitation_scale1p25m_20260727\best.pt'
    )
).Path
$opponents = @(
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\latest.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history500k_allstreet_' +
            'imitation_fullnet_bbweight3_20260726\selected.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history500k_allstreet_' +
            'imitation_fullnet_20260726\best.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\slumbot_free_anchor_position10m_20260727\latest.pt'
        )
    ).Path
)

if (Test-Path -LiteralPath $runDir) {
    throw "Scaled-teacher position output already exists: $runDir"
}
New-Item -ItemType Directory -Path $runDir | Out-Null

$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
$opponentRecords = @(
    foreach ($path in $opponents) {
        [ordered]@{
            path = $path
            sha256 = (
                Get-FileHash -LiteralPath $path -Algorithm SHA256
            ).Hash.ToLowerInvariant()
        }
    }
)
$launcherPath = $MyInvocation.MyCommand.Path
$trainerPath = (
    Resolve-Path -LiteralPath 'scripts\alpha_holdem\train_v5.py'
).Path
$networkPath = (
    Resolve-Path -LiteralPath 'scripts\alpha_holdem\network_hybrid_h1.py'
).Path
$trainArgs = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', '10262472',
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.0001',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.01',
    '--source-policy-kl-coef', '0.5',
    '--separate-preflop-head',
    '--position-adapter-hidden', '256',
    '--position-value-adapter-hidden', '256',
    '--position-adapter-only-training',
    '--position-adapter-training-seat', 'all',
    '--critic-contract', 'critic_v2',
    '--autonomous-critic-v2-reset',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', '0.95',
    '--delta1', '3',
    '--entropy-coef', '0.001',
    '--entropy-floor', '0',
    '--k-best', '3',
    '--pool-strategy', 'latest',
    '--self-play-fraction', '0.3333333333333333',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '6',
    '--fixed-opponent-checkpoints'
) + $opponents + @(
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '100',
    '--save-interval', '20',
    '--archive-checkpoint-every', '100',
    '--run-id', $runId,
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260895',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)

$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    run_id = $runId
    status = if ($WaitForPid -gt 0) { 'WAITING_FOR_GPU_SLOT' } else { 'RUNNING' }
    hypothesis = (
        'The scaled imitation teacher may contain the strongest frozen ' +
        'Slumbot behavior but has narrow opponent coverage and no RL position ' +
        'specialization. Frozen-trunk seat policy/value residual PPO can ' +
        'broaden it without erasing its learned actor.'
    )
    structural_question = (
        'Can a Slumbot-assisted teacher retain its exact source policy while ' +
        'learning general position-specialized residuals from self-play and a ' +
        'diverse league that includes a Slumbot-free opponent?'
    )
    material_change = (
        'Migrate the critic_v1 teacher to a fresh critic_v2, add zero-initialized ' +
        'BB/SB policy and value residuals, freeze the full source actor/trunk, ' +
        'and train the residuals plus critic for 10M environment hands.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    inherited_lineage_training_hands = 262472
    inherited_offline_decision_samples = 1250000
    new_training_hands_target = 10000000
    fixed_opponents = $opponentRecords
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = (
        'SLUMBOT_ASSISTED_WITH_SELFPLAY_AND_SLUMBOT_FREE_LEAGUE_MEMBER'
    )
    evaluation_data_classification = 'FRESH_POST_SOURCE_FREEZE_ONLY'
    position_policy_adapter_hidden = 256
    position_value_adapter_hidden = 256
    frozen_parameters = 'complete scaled-teacher actor and shared representation'
    trainable_parameters = (
        'both position policy residuals, fresh shared critic, and both position ' +
        'value residuals'
    )
    optimizer = [ordered]@{
        algorithm = 'Adam'
        reset_optimizer = $true
        learning_rate = 0.0001
        ppo_epochs = 3
        ppo_target_kl = 0.01
        source_policy_kl_coef = 0.5
        self_play_fraction = (2.0 / 6.0)
        opponent_group_count = 6
    }
    seed = 20260895
    wait_for_pid = $WaitForPid
    command = @('python') + $trainArgs
    launcher = $launcherPath
    launcher_sha256 = (
        Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    trainer_sha256 = (
        Get-FileHash -LiteralPath $trainerPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    network_sha256 = (
        Get-FileHash -LiteralPath $networkPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    migration_smoke = [ordered]@{
        path = (
            'models\smoke_scaledteacher_position_actor_value_' +
            'migration_c1_20260727\latest.pt'
        )
        critic_v1_to_v2 = 'PASS'
        random_rows = 512
        both_seats_actor_bitwise_exact = $true
    }
    evaluator_side_overrides = $false
    started_at = $null
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

if ($WaitForPid -gt 0) {
    Wait-Process -Id $WaitForPid -ErrorAction SilentlyContinue
}
$record.status = 'RUNNING'
$record.started_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

& python @trainArgs
if ($LASTEXITCODE -ne 0) {
    $record.status = 'FAILED'
    $record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
    $record | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $recordPath -Encoding UTF8
    throw 'Scaled-teacher isolated position training failed'
}

$candidate = (
    Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')
).Path
$summary = @(
    & python -X utf8 -c (
        'import sys,torch; ' +
        'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
        'print(int(c[''total_hands''])); ' +
        'print(int(c.get(''position_adapter_hidden'',0))); ' +
        'print(int(c.get(''position_value_adapter_hidden'',0))); ' +
        'print(int(bool(c.get(''position_adapter_only_training'',False))))'
    ) $candidate
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect scaled-teacher position endpoint'
}
$totalHands = [int64]$summary[-4]
if (
    $totalHands -lt 10262472 -or
    [int]$summary[-3] -ne 256 -or
    [int]$summary[-2] -ne 256 -or
    [int]$summary[-1] -ne 1
) {
    throw 'Scaled-teacher position endpoint mismatch'
}

$record.status = 'READY_FOR_INTERNAL_CURVE'
$record.candidate_checkpoint = $candidate
$record.candidate_checkpoint_sha256 = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$record.new_training_hands = $totalHands - 262472
$record.lineage_training_hands = $totalHands
$record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
$record.next = (
    'Run a stable per-seat curve and compare against the frozen scaled teacher, ' +
    'Standard10 and Slumbot-free anchors before any new external hands.'
)
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
