[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ProbeControl', 'ProbeTreatment', 'StageAControl', 'StageATreatment', 'StageBTreatment')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Token = 'fbd630ab6a689913afc1cee8a63066dd'
$Trainer = "C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_lg003_train_${Token}.py"
$Preregistration = "C:\Users\a8594\CardPilot\reports\v5_lg003_cleanroom_diversity_league_preregistration_${Token}_20260723.json"
$PreregistrationSha256 = '525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d'
$Source = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\h11_control_endpoint.pt'
$OutputRoot = "C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_lg003_${Token}_20260723"

$Arm = if ($Mode -in @('ProbeControl', 'StageAControl')) {
    'control_uniform'
} else {
    'treatment_diversity'
}
$Stage = if ($Mode -eq 'StageBTreatment') { 'stageb' } elseif ($Mode -like 'Probe*') { 'probe' } else { 'stagea' }
$TargetHands = if ($Stage -eq 'stageb') { '596021901' } else { '581021901' }
$WallSeconds = if ($Stage -eq 'stageb') { '21600' } else { '10800' }
$RunId = "v5_lg003_${Arm}_${Stage}_${Token}"
$RunDir = Join-Path $OutputRoot "${Arm}_${Stage}"
$Out = Join-Path $RunDir 'latest.pt'
$Provenance = Join-Path $RunDir 'opponent_assignment_provenance.jsonl'

$TrainerArgs = @(
    $Trainer,
    '--lg003-arm', $Arm,
    '--lg003-preregistration', $Preregistration,
    '--lg003-preregistration-sha256', $PreregistrationSha256,
    '--resume', $Source,
    '--allow-resume',
    '--no-reset-optimizer',
    '--device', 'cuda',
    '--workers', '22',
    '--hands-per-iter', '16384',
    '--total-hands', $TargetHands,
    '--starting-stack', '200',
    '--env-version', 'v55',
    '--lr', '0.0003',
    '--ppo-epochs', '4',
    '--ppo-target-kl', '0.03',
    '--mini-batch-size', '1024',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--entropy-coef', '0.05',
    '--entropy-floor', '0.3',
    '--preflop-action-prior-coef', '0.01',
    '--postflop-action-prior-coef', '0.02',
    '--preflop-sb-open-action-prior-coef', '0',
    '--preflop-bb-vs-open-action-prior-coef', '0',
    '--k-best', '5',
    '--pool-strategy', 'loss-kbest',
    '--pool-history-limit', '200',
    '--self-play-fraction', '0.2',
    '--opponent-assignment', 'per-iteration',
    '--opponent-groups', '5',
    '--opponent-assignment-provenance-file', $Provenance,
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '16',
    '--inference-min-batch-slots', '256',
    '--inference-batch-deadline-us', '1000',
    '--worker-seed-base', '73000',
    '--fixed-training-deal-stream',
    '--mirror-self-play-deals',
    '--allin-runout-ev',
    '--allin-runout-ev-max-runouts', '200',
    '--h8-value-head-catchup-after-kl-stop',
    '--critic-contract', 'critic_v1',
    '--value-coef', '0.5',
    '--snapshot-every', '200',
    '--save-interval', '1',
    '--seed', '20260703',
    '--max-runtime-seconds', $WallSeconds,
    '--run-id', $RunId,
    '--run-dir', $RunDir,
    '--out', $Out
)

if ($Mode -like 'Probe*') {
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'LG003 probe requires the registered output root to remain absent.'
    }
    $PriorCuda = [Environment]::GetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'Process')
    $PriorNoBytecode = [Environment]::GetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', '-1', 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', '1', 'Process')
        & $Python @TrainerArgs '--lg003-contract-probe'
        if ($LASTEXITCODE -ne 0) {
            throw "LG003 probe child exit $LASTEXITCODE"
        }
    } finally {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', $PriorCuda, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', $PriorNoBytecode, 'Process')
    }
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'LG003 probe created the registered output root.'
    }
    exit 0
}

if (Test-Path -LiteralPath $RunDir) {
    throw "LG003 refuses to overwrite existing run directory: $RunDir"
}
& $Python @TrainerArgs
exit $LASTEXITCODE
