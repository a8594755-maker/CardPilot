# Canonical CT002 ae78 launcher. All paths are absolute and launcher-owned.

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'BuildData', 'Calibrate', 'Mechanism', 'Ppo')]
    [string]$Mode,

    [ValidateSet('', 'control', 'treatment')]
    [string]$Arm = '',

    [string]$ImplementationAuditSha256 = ''
)

$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_ct002_runner_ae78e683c41a2abcff33eeae9fdad8ad.py'
$Preregistration = 'C:\Users\a8594\CardPilot\reports\v5_ct002_preregistration_ae78e683c41a2abcff33eeae9fdad8ad_20260722.json'
$PreregistrationAudit = 'C:\Users\a8594\CardPilot\reports\v5_ct002_preregistration_audit_ae78e683c41a2abcff33eeae9fdad8ad_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_ct002_implementation_audit_result_ae78e683c41a2abcff33eeae9fdad8ad_20260722.json'
$SourceCheckpoint = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715\latest.pt'
$OutputRoot = 'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_hybrid\v5_ct002_ae78e683c41a2abcff33eeae9fdad8ad_20260722'

foreach ($Path in @($Python, $Runner, $Preregistration, $PreregistrationAudit, $SourceCheckpoint)) {
    if (-not [System.IO.Path]::IsPathRooted($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "CT002 absolute required input missing: $Path"
    }
}
if (-not [System.IO.Path]::IsPathRooted($OutputRoot)) {
    throw 'CT002 output root must be absolute'
}

Remove-Item Env:CUDA_VISIBLE_DEVICES -ErrorAction SilentlyContinue
Remove-Item Env:CT002_DEVICE_MODE -ErrorAction SilentlyContinue
Remove-Item Env:CT002_CONTRACT_NONCE -ErrorAction SilentlyContinue
$env:PYTHONDONTWRITEBYTECODE = '1'

$CommonArguments = @(
    '-B', $Runner,
    '--preregistration', $Preregistration,
    '--preregistration-audit', $PreregistrationAudit,
    '--source-checkpoint', $SourceCheckpoint,
    '--output-root', $OutputRoot
)

if ($Mode -eq 'ContractProbe') {
    if ($Arm -notin @('control', 'treatment')) {
        throw 'ContractProbe requires -Arm control or treatment'
    }
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'ContractProbe forbids an existing CT002 output root'
    }
    if (Test-Path -LiteralPath $ImplementationAudit) {
        throw 'ContractProbe must precede immutable implementation-audit result write'
    }
    $env:CUDA_VISIBLE_DEVICES = '-1'
    $env:CT002_DEVICE_MODE = 'CPU_ONLY_NO_GPU_NO_OUTPUT'
    $Nonce = if ($Arm -eq 'control') { '2026072213' } else { '2026072214' }
    $env:CT002_CONTRACT_NONCE = $Nonce
    & $Python @CommonArguments --mode contract-probe --arm $Arm --nonce $Nonce
    exit $LASTEXITCODE
}

if (-not [regex]::IsMatch($ImplementationAuditSha256, '^[0-9a-f]{64}$')) {
    throw "$Mode requires -ImplementationAuditSha256 as 64 lowercase hexadecimal characters"
}
if (-not (Test-Path -LiteralPath $ImplementationAudit -PathType Leaf)) {
    throw 'Canonical CT002 implementation-audit result is missing'
}
$ObservedAuditSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ImplementationAudit).Hash.ToLowerInvariant()
if ($ObservedAuditSha256 -ne $ImplementationAuditSha256) {
    throw 'Canonical CT002 implementation-audit hash mismatch'
}

$env:CUDA_VISIBLE_DEVICES = '0'
$env:CT002_DEVICE_MODE = 'CUDA_SINGLE_GPU_SEQUENTIAL_NO_FALLBACK'

switch ($Mode) {
    'BuildData' {
        if ($Arm -ne '') { throw 'BuildData forbids -Arm' }
        if (Test-Path -LiteralPath $OutputRoot) { throw 'BuildData output collision' }
        & $Python @CommonArguments --mode build-data
        exit $LASTEXITCODE
    }
    'Calibrate' {
        if ($Arm -notin @('control', 'treatment')) { throw 'Calibrate requires an arm' }
        & $Python @CommonArguments --mode calibrate --arm $Arm
        exit $LASTEXITCODE
    }
    'Mechanism' {
        if ($Arm -ne '') { throw 'Mechanism forbids -Arm' }
        & $Python @CommonArguments --mode mechanism
        exit $LASTEXITCODE
    }
    'Ppo' {
        if ($Arm -notin @('control', 'treatment')) { throw 'Ppo requires an arm' }
        & $Python @CommonArguments --mode ppo --arm $Arm
        exit $LASTEXITCODE
    }
}

throw 'Unreachable CT002 launcher mode'
