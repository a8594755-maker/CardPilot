param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('ContractProbe', 'Qualification', 'Audit')]
    [string]$Mode,

    [Parameter(Mandatory = $false)]
    [string]$ProbeNonce = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Python = 'C:\Users\a8594\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_fa002_q01_61e5047f8820e9df19733e57c257a04a.py'
$Auditor = 'C:\Users\a8594\CardPilot\scripts\alpha_holdem\v5_fa002_q01_audit_61e5047f8820e9df19733e57c257a04a.py'
$Preregistration = 'C:\Users\a8594\CardPilot\reports\v5_fa002_unified_candidate_preregistration_61e5047f8820e9df19733e57c257a04a_20260722.json'
$PreregistrationAudit = 'C:\Users\a8594\CardPilot\reports\v5_fa002_unified_candidate_preregistration_audit_61e5047f8820e9df19733e57c257a04a_20260722.json'
$ImplementationAudit = 'C:\Users\a8594\CardPilot\reports\v5_fa002_q01_implementation_audit_61e5047f8820e9df19733e57c257a04a_20260722.json'
$OutputRoot = 'C:\Users\a8594\CardPilot\reports\v5_fa002_q01_61e5047f8820e9df19733e57c257a04a_20260722'
$ExecutionNonce = 'FA002_Q01_EXECUTION_2034972233'
$AllowedProbeNonces = @(
    'FA002_Q01_PROBE_A_2032972233',
    'FA002_Q01_PROBE_B_2033972233'
)

foreach ($RequiredPath in @($Python, $Runner, $Preregistration, $PreregistrationAudit)) {
    if (-not (Test-Path -LiteralPath $RequiredPath -PathType Leaf)) {
        throw "required_file_absent:$RequiredPath"
    }
}

$env:CUDA_VISIBLE_DEVICES = '-1'
$env:FA002_Q01_DEVICE_MODE = 'CPU_ONLY_NO_TORCH_NO_GPU_NO_FALLBACK'

if ($Mode -eq 'ContractProbe') {
    if ($AllowedProbeNonces -notcontains $ProbeNonce) {
        throw 'probe_nonce_not_registered'
    }
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'qualification_output_root_exists_before_probe'
    }
    $env:FA002_Q01_CONTRACT_NONCE = $ProbeNonce
    & $Python $Runner `
        --mode ContractProbe `
        --expected-nonce $ProbeNonce
    exit $LASTEXITCODE
}

if ($ProbeNonce -ne '') {
    throw 'probe_nonce_forbidden_outside_contract_probe'
}

if (-not (Test-Path -LiteralPath $ImplementationAudit -PathType Leaf)) {
    throw 'implementation_audit_absent'
}
$ImplementationAuditSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $ImplementationAudit).Hash.ToLowerInvariant()

if ($Mode -eq 'Qualification') {
    if (Test-Path -LiteralPath $OutputRoot) {
        throw 'qualification_output_root_exists'
    }
    $env:FA002_Q01_CONTRACT_NONCE = $ExecutionNonce
    & $Python $Runner `
        --mode Qualification `
        --expected-nonce $ExecutionNonce `
        --preregistration $Preregistration `
        --preregistration-audit $PreregistrationAudit `
        --implementation-audit $ImplementationAudit `
        --implementation-audit-sha256 $ImplementationAuditSha256 `
        --output $OutputRoot
    exit $LASTEXITCODE
}

if (-not (Test-Path -LiteralPath $Auditor -PathType Leaf)) {
    throw 'result_auditor_absent'
}
if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container)) {
    throw 'qualification_output_root_absent'
}
$env:FA002_Q01_CONTRACT_NONCE = $ExecutionNonce
& $Python $Auditor `
    --root $OutputRoot `
    --preregistration $Preregistration `
    --preregistration-audit $PreregistrationAudit `
    --implementation-audit $ImplementationAudit `
    --implementation-audit-sha256 $ImplementationAuditSha256
exit $LASTEXITCODE
