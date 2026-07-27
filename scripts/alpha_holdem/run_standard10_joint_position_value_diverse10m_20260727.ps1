param(
    [int]$WaitForPid = 0
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$runId = 'sourcev4_standard10_joint_position_value_diverse10m_20260727'
$runDir = Join-Path 'models' $runId
$recordPath = Join-Path $runDir 'experiment_record.json'
$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\latest.pt'
    )
).Path
$opponents = @(
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history_allstreet_' +
            'imitation_scale1p25m_20260727\best.pt'
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
    throw "Position-value output already exists: $runDir"
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
    '--total-hands', '20283876',
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.00001',
    '--preflop-head-lr', '0.000003',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.006',
    '--source-policy-kl-coef', '2',
    '--separate-preflop-head',
    '--position-adapter-hidden', '256',
    '--position-value-adapter-hidden', '256',
    '--critic-contract', 'critic_v2',
    '--autonomous-critic-v2-continue',
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
    '--seed', '20260891',
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
        'The Standard10 SB/BB gap partly comes from a shared critic aliasing ' +
        'BB/OOP and SB/IP returns. Seat-specific zero-residual value heads ' +
        'should improve credit assignment beyond policy-only position heads.'
    )
    structural_question = (
        'Does position-conditioned credit assignment improve greedy policy ' +
        'learning when source, seed, league, actor architecture and budget ' +
        'match the policy-only joint-trunk experiment?'
    )
    material_change = (
        'Relative to the matched joint-trunk experiment, add only two ' +
        'zero-initialized 256-hidden BB/SB value residual heads.'
    )
    matched_control = (
        'models\sourcev4_standard10_joint_trunk_position_diverse10m_20260727'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    inherited_lineage_training_hands = 10283876
    inherited_offline_decision_samples = 750000
    new_training_hands_target = 10000000
    fixed_opponents = $opponentRecords
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = (
        'SLUMBOT_ASSISTED_WITH_SLUMBOT_FREE_LEAGUE_MEMBER'
    )
    position_policy_adapter_hidden = 256
    position_value_adapter_hidden = 256
    trainable_parameters = (
        'complete shared actor, both position policy heads, shared critic, ' +
        'and both position value heads'
    )
    optimizer = [ordered]@{
        algorithm = 'Adam'
        reset_optimizer = $true
        learning_rate = 0.00001
        preflop_head_learning_rate = 0.000003
        ppo_epochs = 3
        ppo_target_kl = 0.006
        source_policy_kl_coef = 2.0
        self_play_fraction = (2.0 / 6.0)
        opponent_group_count = 6
    }
    seed = 20260891
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
    throw 'Joint position-value 10M training failed'
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
        'print(int(c.get(''position_value_adapter_hidden'',0)))'
    ) $candidate
)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect position-value endpoint'
}
$totalHands = [int64]$summary[-3]
if (
    $totalHands -lt 20283876 -or
    [int]$summary[-2] -ne 256 -or
    [int]$summary[-1] -ne 256
) {
    throw 'Position-value endpoint mismatch'
}

$record.status = 'READY_FOR_INTERNAL_CURVE'
$record.candidate_checkpoint = $candidate
$record.candidate_checkpoint_sha256 = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$record.new_training_hands = $totalHands - 10283876
$record.lineage_training_hands = $totalHands
$record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
$record.next = (
    'Run the stable paired per-seat curve against the matched policy-only ' +
    'control before allocating fresh Slumbot hands.'
)
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
