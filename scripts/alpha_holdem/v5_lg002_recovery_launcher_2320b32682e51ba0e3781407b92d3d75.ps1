[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'StageAControl', 'StageATreatment')]
    [string]$Mode,

    [ValidateSet('control_uniform', 'treatment_diversity')]
    [string]$Arm = 'control_uniform'
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Trainer = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\train_v5.py'
$Preregistration = 'C:\Users\a8594\CardPilot\reports\v5_lg002_recovery_preregistration_2320b32682e51ba0e3781407b92d3d75_20260722.json'
$PreregistrationSha256 = 'ef41b731de6ad74f93d01cbb2f4ce245bcde9323335e331a6c31f0daf3e9eda9'
$Source = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\latest.pt'
$OutputRoot = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_lg002_recovery_2320b32682e51ba0e3781407b92d3d75_20260722'

if ($Mode -eq 'StageAControl') {
    $Arm = 'control_uniform'
} elseif ($Mode -eq 'StageATreatment') {
    $Arm = 'treatment_diversity'
}

$RunId = "v5_lg002_recovery_${Arm}_5m_2320b32682e51ba0e3781407b92d3d75"
$RunDir = Join-Path $OutputRoot $Arm
$Out = Join-Path $RunDir 'latest.pt'
$Provenance = Join-Path $RunDir 'opponent_assignment_provenance.jsonl'

$TrainerArgs = @(
    $Trainer,
    '--lg002-recovery-arm', $Arm,
    '--lg002-recovery-preregistration', $Preregistration,
    '--lg002-recovery-preregistration-sha256', $PreregistrationSha256,
    '--resume', $Source,
    '--allow-resume',
    '--no-reset-optimizer',
    '--device', 'cuda',
    '--workers', '22',
    '--hands-per-iter', '16384',
    '--total-hands', '581021901',
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
    '--max-runtime-seconds', '10800',
    '--run-id', $RunId,
    '--run-dir', $RunDir,
    '--out', $Out
)

if ($Mode -eq 'ContractProbe') {
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'LG002 ContractProbe requires the registered output root to remain absent.'
    }
    $PriorCuda = [Environment]::GetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'Process')
    $PriorNoBytecode = [Environment]::GetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', '-1', 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', '1', 'Process')
        & $Python @TrainerArgs '--lg002-recovery-contract-probe'
        if ($LASTEXITCODE -ne 0) { throw "LG002 ContractProbe child exit $LASTEXITCODE" }
    } finally {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', $PriorCuda, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', $PriorNoBytecode, 'Process')
    }
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'LG002 ContractProbe created the forbidden registered output root.'
    }
    exit 0
}

& $Python @TrainerArgs
exit $LASTEXITCODE
