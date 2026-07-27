param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('control_uniform', 'treatment_diversity')]
    [string]$Arm,

    [Parameter(Mandatory = $true)]
    [ValidateSet('stage_a', 'stage_b')]
    [string]$Stage,

    [switch]$ContractOnly
)

$ErrorActionPreference = 'Stop'
$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$PythonSha256 = '4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a'
$Trainer = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\train_v5_hybrid_h1.py'
$TrainerSha256 = '91a98cec7677f4ee2ba74491f1be61ef2b3d4bfbb574b3615604d45f569d5591'
$Contract = 'C:\Users\a8594\CardPilot\reports\v5_lg001_unified_behavior_window_preregistration_5ee42cb09c534cb3a294be701e94047f_20260722.json'
$ContractSha256 = '2d0a306ae005028a0745012dba5711316defee7f57bc1e2663e6726135be4125'
$Source = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\h11_control_endpoint.pt'
$SourceSha256 = '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13'
$Root = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_lg001_5ee42cb09c534cb3a294be701e94047f_20260722'
$ExpectedGpuUuid = 'GPU-01d41f66-6148-83e4-ce86-8b0c15f8a60d'

if ($Arm -eq 'control_uniform' -and $Stage -ne 'stage_a') {
    throw 'LG001 control_uniform is registered only for stage_a.'
}

if ((Get-FileHash -LiteralPath $Python -Algorithm SHA256).Hash.ToLower() -ne $PythonSha256) {
    throw 'LG001 exact Python hash mismatch.'
}
if ((Get-FileHash -LiteralPath $Trainer -Algorithm SHA256).Hash.ToLower() -ne $TrainerSha256) {
    throw 'LG001 trainer hash mismatch.'
}
if ((Get-FileHash -LiteralPath $Contract -Algorithm SHA256).Hash.ToLower() -ne $ContractSha256) {
    throw 'LG001 preregistration hash mismatch.'
}

$GpuRows = @(& nvidia-smi --query-gpu=index,name,uuid,memory.total --format=csv,noheader,nounits)
if ($LASTEXITCODE -ne 0 -or $GpuRows.Count -ne 1) {
    throw 'LG001 requires exactly one queryable registered GPU.'
}
$GpuFields = @($GpuRows[0].Split(',') | ForEach-Object { $_.Trim() })
if ($GpuFields.Count -ne 4 -or $GpuFields[0] -ne '0' -or $GpuFields[1] -ne 'NVIDIA GeForce RTX 4070' -or $GpuFields[2] -ne $ExpectedGpuUuid -or $GpuFields[3] -ne '12282') {
    throw "LG001 GPU identity mismatch: $($GpuRows[0])"
}

$OtherPython = @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(w)?\.exe$' })
if ($OtherPython.Count -ne 0 -and -not $ContractOnly) {
    throw 'LG001 resource isolation failed: another Python process exists.'
}

if ($Stage -eq 'stage_a') {
    $TargetHands = '581021901'
    $MaxRuntime = '10800'
    $Resume = $Source
    $RunLeaf = if ($Arm -eq 'control_uniform') { 'control_uniform_5m' } else { 'treatment_diversity_5m' }
    if ((Get-FileHash -LiteralPath $Resume -Algorithm SHA256).Hash.ToLower() -ne $SourceSha256) {
        throw 'LG001 Stage A source checkpoint hash mismatch.'
    }
} else {
    $TargetHands = '596021901'
    $MaxRuntime = '21600'
    $Resume = Join-Path $Root 'treatment_diversity_5m\latest.pt'
    $RunLeaf = 'treatment_diversity_20m'
    if (-not (Test-Path -LiteralPath $Resume -PathType Leaf)) {
        throw 'LG001 Stage B requires the exact Stage A treatment endpoint.'
    }
}

$RunDir = Join-Path $Root $RunLeaf
$Out = Join-Path $RunDir 'latest.pt'
$Provenance = Join-Path $RunDir 'opponent_assignment_provenance.jsonl'
$RunId = "lg001_5ee42cb09c534cb3a294be701e94047f_${Arm}_${Stage}"
if (Test-Path -LiteralPath $RunDir) {
    throw "LG001 single-attempt output collision: $RunDir"
}

$env:CUDA_VISIBLE_DEVICES = '0'
$TrainerArgs = @(
    '-B', $Trainer,
    '--device', 'cuda',
    '--workers', '22',
    '--hands-per-iter', '16384',
    '--total-hands', $TargetHands,
    '--starting-stack', '200',
    '--env-version', 'v55',
    '--lr', '0.0003',
    '--ppo-epochs', '4',
    '--mini-batch-size', '1024',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--delta1', '3',
    '--entropy-coef', '0.05',
    '--entropy-floor', '0.3',
    '--postflop-action-prior-coef', '0.02',
    '--postflop-action-prior-target', '0.15,0.30,0.52,0.03',
    '--preflop-action-prior-coef', '0.01',
    '--preflop-action-prior-target', '0.24,0.36,0.38,0.02',
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
    '--critic-contract', 'critic_v1',
    '--h1-effective-stack-divisor', '200',
    '--h1-critic-init-seed', '2026071102',
    '--value-coef', '0.5',
    '--snapshot-every', '200',
    '--save-interval', '1',
    '--run-id', $RunId,
    '--run-dir', $RunDir,
    '--out', $Out,
    '--seed', '20260703',
    '--max-runtime-seconds', $MaxRuntime,
    '--resume', $Resume,
    '--allow-resume',
    '--no-reset-optimizer',
    '--lg001-contract', $Contract,
    '--lg001-arm', $Arm
)

if ($ContractOnly) {
    [pscustomobject]@{
        classification = 'LG001_LAUNCH_CONTRACT_PASS_NO_CHILD_NO_OUTPUT'
        arm = $Arm
        stage = $Stage
        run_dir = $RunDir
        target_hands = [int64]$TargetHands
        cuda_visible_devices_parent = $env:CUDA_VISIBLE_DEVICES
        gpu_uuid = $ExpectedGpuUuid
        trainer_sha256 = $TrainerSha256
        contract_sha256 = $ContractSha256
        child_started = $false
        other_python_processes_observed = $OtherPython.Count
        files_written = 0
    } | ConvertTo-Json -Depth 4
    exit 0
}

$ArgumentString = ($TrainerArgs | ForEach-Object {
    if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
}) -join ' '
$Process = Start-Process -FilePath $Python -ArgumentList $ArgumentString -PassThru -WindowStyle Hidden
try {
    $Process.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
} catch {
    Stop-Process -Id $Process.Id -Force
    throw 'LG001 could not set child priority BelowNormal.'
}
$Process.WaitForExit()
if ($Process.ExitCode -ne 0) {
    throw "LG001 trainer exited $($Process.ExitCode). No automatic restart is allowed."
}
exit 0
