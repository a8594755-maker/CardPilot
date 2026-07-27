[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Probe', 'StageA')]
    [string]$Mode
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Repo = 'C:\Users\a8594\CardPilot'
$Token = 'dbc03bbf7d1d9cb0270c4b1f9d583a58'
$Identity = 'dbc03bbf7d1d9cb0270c4b1f9d583a586b82c23a655de48a4fb2139ac00a3fb1'
$Preregistration = Join-Path $Repo "reports\v5_vr002_corrected_faithful_qboost_preregistration_${Token}_20260723.json"
$PreregistrationSha256 = '029411e18760455197471a12f0c00c07d08e6d3123e3d8d62e4b51bc6b7b6fcd'
$PreimplementationAudit = Join-Path $Repo "reports\v5_vr002_corrected_faithful_qboost_preregistration_audit_${Token}_20260723.json"
$PreimplementationAuditSha256 = 'fe45bd5235f4be3130616b3a387db7a3b41df9f9bfaf9eb44b2bd0d65ec876c6'
$ImplementationAudit = Join-Path $Repo "reports\v5_vr002_implementation_audit_${Token}_20260723.json"
$Core = Join-Path $Repo "scripts\alpha_holdem\v5_vr002_qboost_core_${Token}.py"
$Trainer = Join-Path $Repo "scripts\alpha_holdem\v5_vr002_train_${Token}.py"
$ParentPreregistration = Join-Path $Repo 'reports\v5_lg003_cleanroom_diversity_league_preregistration_fbd630ab6a689913afc1cee8a63066dd_20260723.json'
$ParentPreregistrationSha256 = '525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d'
$Source = Join-Path $Repo 'models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\h11_control_endpoint.pt'
$SourceSha256 = '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13'
$OutputRoot = Join-Path $Repo "models\alpha_holdem_v5_hybrid\v5_vr002_${Token}_20260723"
$RunDir = Join-Path $OutputRoot 'vrpo_stagea'
$Out = Join-Path $RunDir 'latest.pt'
$Provenance = Join-Path $RunDir 'opponent_assignment_provenance.jsonl'
$RunId = "v5_vr002_qboost_stagea_${Token}"

function Assert-Hash([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "VR002 missing ${Label}: $Path"
    }
    $Actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) {
        throw "VR002 ${Label} hash mismatch: expected $Expected got $Actual"
    }
}

Assert-Hash $Preregistration $PreregistrationSha256 'preregistration'
Assert-Hash $PreimplementationAudit $PreimplementationAuditSha256 'preimplementation audit'
Assert-Hash $ParentPreregistration $ParentPreregistrationSha256 'parent preregistration'
Assert-Hash $Source $SourceSha256 'source checkpoint'
if (-not (Test-Path -LiteralPath $Core -PathType Leaf)) { throw "VR002 core absent: $Core" }
if (-not (Test-Path -LiteralPath $Trainer -PathType Leaf)) { throw "VR002 trainer absent: $Trainer" }

$TrainerArgs = @(
    $Trainer,
    '--vr002-preregistration', $Preregistration,
    '--vr002-preregistration-sha256', $PreregistrationSha256,
    '--vr002-q-init-seed', '2026072302',
    '--vr002-q-minibatch-seed', '2026072303',
    '--vr002-actor-generation-initial', '35051',
    '--lg003-arm', 'control_uniform',
    '--lg003-preregistration', $ParentPreregistration,
    '--lg003-preregistration-sha256', $ParentPreregistrationSha256,
    '--resume', $Source, '--allow-resume', '--no-reset-optimizer',
    '--device', 'cuda', '--workers', '22', '--hands-per-iter', '16384',
    '--total-hands', '581021901', '--starting-stack', '200', '--env-version', 'v55',
    '--lr', '0.0003', '--ppo-epochs', '4', '--ppo-target-kl', '0.03',
    '--mini-batch-size', '1024', '--epsilon', '0', '--gamma', '0.999',
    '--entropy-coef', '0.05', '--entropy-floor', '0.3',
    '--preflop-action-prior-coef', '0.01', '--postflop-action-prior-coef', '0.02',
    '--preflop-sb-open-action-prior-coef', '0',
    '--preflop-bb-vs-open-action-prior-coef', '0',
    '--k-best', '5', '--pool-strategy', 'loss-kbest', '--pool-history-limit', '200',
    '--self-play-fraction', '0.2', '--opponent-assignment', 'per-iteration',
    '--opponent-groups', '5',
    '--opponent-assignment-provenance-file', $Provenance,
    '--rollout-mode', 'multi',
    '--critic-contract', 'critic_v1', '--value-coef', '0', '--snapshot-every', '200',
    '--max-grad-norm', '0.5', '--rollout-envs-per-worker', '16',
    '--inference-min-batch-slots', '256', '--inference-batch-deadline-us', '1000',
    '--worker-seed-base', '73000', '--fixed-training-deal-stream',
    '--mirror-self-play-deals', '--allin-runout-ev', '--allin-runout-ev-max-runouts', '200',
    '--save-interval', '1',
    '--seed', '20260703', '--max-runtime-seconds', '21600',
    '--run-id', $RunId, '--run-dir', $RunDir, '--out', $Out
)

if ($Mode -eq 'Probe') {
    if (Test-Path -LiteralPath $OutputRoot) { throw 'VR002 probe output-root collision.' }
    $PriorCuda = [Environment]::GetEnvironmentVariable('CUDA_VISIBLE_DEVICES', 'Process')
    $PriorNoBytecode = [Environment]::GetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', 'Process')
    try {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', '-1', 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', '1', 'Process')
        & $Python @TrainerArgs '--vr002-contract-probe'
        if ($LASTEXITCODE -ne 0) { throw "VR002 probe child exit $LASTEXITCODE" }
    } finally {
        [Environment]::SetEnvironmentVariable('CUDA_VISIBLE_DEVICES', $PriorCuda, 'Process')
        [Environment]::SetEnvironmentVariable('PYTHONDONTWRITEBYTECODE', $PriorNoBytecode, 'Process')
    }
    if (Test-Path -LiteralPath $OutputRoot) { throw 'VR002 probe wrote output.' }
    exit 0
}

if (Test-Path -LiteralPath $OutputRoot) {
    throw "VR002 StageA output-root collision: $OutputRoot"
}
if (-not (Test-Path -LiteralPath $ImplementationAudit -PathType Leaf)) {
    throw 'VR002 StageA requires the frozen implementation-audit report.'
}
$Audit = Get-Content -LiteralPath $ImplementationAudit -Raw | ConvertFrom-Json
if ($Audit.status -ne 'VR002_IMPLEMENTATION_AUDIT_PASS_STAGEA_AUTHORIZED') {
    throw "VR002 implementation audit is not launch-authorizing: $($Audit.status)"
}
if ($Audit.identity_sha256 -ne $Identity -or $Audit.preregistration_sha256 -ne $PreregistrationSha256) {
    throw 'VR002 implementation-audit identity mismatch.'
}
$CurrentCoreSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Core).Hash.ToLowerInvariant()
$CurrentTrainerSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Trainer).Hash.ToLowerInvariant()
$CurrentLauncherSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $PSCommandPath).Hash.ToLowerInvariant()
$WindowAuditor = Join-Path $Repo "scripts\alpha_holdem\v5_vr002_window_audit_${Token}.py"
$CurrentWindowAuditorSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $WindowAuditor).Hash.ToLowerInvariant()
if (
    $Audit.artifacts.core.sha256 -ne $CurrentCoreSha -or
    $Audit.artifacts.trainer.sha256 -ne $CurrentTrainerSha -or
    $Audit.artifacts.launcher.sha256 -ne $CurrentLauncherSha -or
    $Audit.artifacts.window_auditor.sha256 -ne $CurrentWindowAuditorSha
) {
    throw 'VR002 implementation source changed after audit.'
}

& $Python @TrainerArgs
exit $LASTEXITCODE
